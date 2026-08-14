from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from workbench.diagnostics.redaction import redact_text
from workbench.domain.enums import JobStatus, JobType
from workbench.domain.models import AuditEvent, JobRecord
from workbench.exports.video_profiles import ExportProfileBlocked
from workbench.jobs.execution import (
    PersistentRenderExecutionContext,
    RenderCancelled,
    RenderPauseRequested,
)
from workbench.jobs.repository import JobRepository, JobSpec
from workbench.rendering.export_pipeline import GraphExportBlocked, GraphExportError
from workbench.rendering.feature_flags import RenderFeatureFlags
from workbench.rendering.hashing import sha256_json
from workbench.rendering.models import RenderGraphV2
from workbench.rendering.preflight import GraphPreflight
from workbench.rendering.snapshot_store import RenderGraphSnapshotStore

from .errors import (
    FfmpegConcatFailed,
    FfmpegMuxFailed,
    MediaValidationFailed,
    PackageValidationFailed,
    RenderDiskFull,
    RendererRuntimeUnavailable,
    RenderInputChanged,
    RenderInputStale,
    RenderPageFailed,
)
from .fingerprint import render_input_fingerprint
from .models import ProjectVideoProps
from .package_service import VideoExportBlocked, VideoExportService
from .preview_service import VideoPreviewService


@dataclass(frozen=True)
class RenderJobSubmission:
    job: JobRecord
    created: bool


RenderSubmitResult = RenderJobSubmission
ERROR_CODE_BY_EXCEPTION = {
    RenderInputStale: "render_input_stale",
    RenderInputChanged: "render_input_changed",
    RendererRuntimeUnavailable: "renderer_runtime_unavailable",
    RenderPageFailed: "render_page_failed",
    FfmpegMuxFailed: "ffmpeg_mux_failed",
    FfmpegConcatFailed: "ffmpeg_concat_failed",
    MediaValidationFailed: "media_validation_failed",
    PackageValidationFailed: "package_validation_failed",
    RenderDiskFull: "render_disk_full",
    GraphExportBlocked: "render_graph_preflight_blocked",
    GraphExportError: "render_graph_export_failed",
}


class RenderJobWorkerProtocol(Protocol):
    enabled: bool

    def wake(self) -> None: ...


class ExportProfileResolver(Protocol):
    def __call__(self, props: ProjectVideoProps, preset_id: str) -> ProjectVideoProps: ...


class RenderJobService:
    def __init__(
        self,
        projects: Any,
        preview: VideoPreviewService,
        exporter: VideoExportService,
        *,
        repository: JobRepository | None = None,
        graph_provider: Callable[[UUID], RenderGraphV2] | None = None,
        graph_exporter: Callable[[UUID, RenderGraphV2, PersistentRenderExecutionContext], Any]
        | None = None,
        feature_flags: RenderFeatureFlags | None = None,
        profile_resolver: ExportProfileResolver | None = None,
    ) -> None:
        self.projects = projects
        self.preview = preview
        self.exporter = exporter
        self.renderer = exporter
        self.repository = repository or projects.jobs
        self.worker: RenderJobWorkerProtocol | None = None
        self.graph_provider = graph_provider
        self.graph_exporter = graph_exporter
        self.feature_flags = feature_flags or RenderFeatureFlags.from_environment()
        self.profile_resolver = profile_resolver

    def act(
        self,
        project_id: UUID,
        job_id: UUID,
        action: str,
        *,
        expected_revision: int | None = None,
    ) -> RenderJobSubmission:
        job = self.repository.get(job_id)
        if job.project_id != project_id:
            raise KeyError(job_id)
        if action == "pause":
            updated = self.repository.request_pause(
                job_id, expected_revision=expected_revision
            )
            audit = "video_render_job_pause_requested"
        elif action == "resume":
            updated = self.repository.resume(job_id, expected_revision=expected_revision)
            audit = "video_render_job_resumed"
        elif action == "cancel":
            updated = self.repository.request_cancel(
                job_id, expected_revision=expected_revision
            )
            audit = "video_render_job_cancel_requested"
        elif action == "retry":
            submission = self.retry(job_id)
            if submission.created and self.worker is not None:
                self.worker.wake()
            return submission
        else:
            raise ValueError(f"unsupported action: {action}")
        self._audit(project_id, audit, {"job_id": str(job_id)})
        if updated.status is JobStatus.QUEUED and self.worker is not None:
            self.worker.wake()
        return RenderJobSubmission(updated, False)

    def submit(
        self,
        project_id: UUID,
        *,
        idempotency_key: str | None = None,
        preset_id: str | None = None,
    ) -> RenderJobSubmission:
        project = self.projects.get(project_id)
        if (
            self.feature_flags.export
            and self.feature_flags.renderer_generation == "v2"
            and self.graph_provider is not None
        ):
            return self._submit_v2(project, project_id, idempotency_key=idempotency_key)
        preflight = self.preview.preflight(project_id)
        if not preflight.allowed or preflight.props is None:
            raise VideoExportBlocked("video preflight is not complete")
        props = preflight.props
        if preset_id is not None:
            if self.profile_resolver is None:
                raise VideoExportBlocked("export profile admission is not configured")
            try:
                props = self.profile_resolver(props, preset_id)
            except ExportProfileBlocked as error:
                raise VideoExportBlocked(str(error)) from error
        effective_preflight = (
            preflight.model_copy(update={"props": props}) if preset_id is not None else preflight
        )
        fingerprint = render_input_fingerprint(effective_preflight)
        payload: dict[str, object] = {"props": props.model_dump(mode="json")}
        if preset_id is not None:
            payload["preset_id"] = preset_id
        spec = JobSpec(
            project_id=project_id,
            job_type=JobType.EXPORT_PACKAGE,
            cache_key=f"export-package:{fingerprint}",
            input_fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            payload=payload,
        )
        result = self.repository.enqueue_or_get(spec)
        if (
            not result.created
            and result.record.status is JobStatus.SUCCEEDED
            and not self._published_result_is_valid(project, result.record)
        ):
            result = self.repository.enqueue_or_get(spec, reuse_succeeded=False)
        if result.created:
            self._write_input_snapshot(project, result.record, props)
            self._audit(
                project_id,
                "video_render_job_created",
                {"job_id": str(result.record.id), "preset_id": preset_id},
            )
        return RenderJobSubmission(result.record, result.created)

    def _submit_v2(
        self,
        project: Any,
        project_id: UUID,
        *,
        idempotency_key: str | None,
    ) -> RenderJobSubmission:
        graph = self.graph_provider(project_id)  # type: ignore[misc]
        root = (self.projects.workspace_root / project.project_dir).resolve()
        report = GraphPreflight().check(
            graph,
            root,
            strict_assets=self.feature_flags.strict_assets,
        )
        if not report.allowed:
            raise VideoExportBlocked("RenderGraph V2 导出预检未通过")
        snapshot = RenderGraphSnapshotStore(root).set_current(project_id, graph)
        fingerprint = sha256_json(
            {
                "graph_hash": graph.graph_hash,
                "renderer_generation": "v2",
                "runtime": "rendergraph-v2",
            }
        )
        spec = JobSpec(
            project_id=project_id,
            job_type=JobType.EXPORT_PACKAGE,
            cache_key=f"export-package:v2:{fingerprint}",
            input_fingerprint=fingerprint,
            idempotency_key=idempotency_key,
            payload={
                "render_generation": "v2",
                "graph_id": str(graph.graph_id),
                "graph_hash": graph.graph_hash,
                "graph_snapshot_relative_path": snapshot.relative_to(root).as_posix(),
            },
        )
        result = self.repository.enqueue_or_get(spec)
        if (
            not result.created
            and result.record.status is JobStatus.SUCCEEDED
            and not self._published_result_is_valid(project, result.record)
        ):
            result = self.repository.enqueue_or_get(spec, reuse_succeeded=False)
        if result.created:
            self._write_graph_input_snapshot(root, result.record, graph)
            self._audit(
                project_id,
                "video_render_graph_job_created",
                {"job_id": str(result.record.id), "graph_hash": graph.graph_hash},
            )
        return RenderJobSubmission(result.record, result.created)

    def retry(self, job_id: UUID) -> RenderJobSubmission:
        previous = self.repository.get(job_id)
        if previous.status not in {JobStatus.FAILED, JobStatus.CANCELLED}:
            raise ValueError("only failed or cancelled jobs can be retried")
        result = self.repository.enqueue_or_get(
            JobSpec(
                project_id=previous.project_id,
                job_type=previous.job_type,
                cache_key=previous.cache_key,
                input_fingerprint=previous.input_fingerprint,
                payload=previous.payload,
                parent_job_id=previous.id,
                paid=previous.paid,
                max_attempts=previous.max_attempts,
            )
        )
        return RenderJobSubmission(result.record, result.created)

    def handle(self, record: JobRecord) -> None:
        if self.repository.get(record.id).status is JobStatus.QUEUED:
            self.repository.mark_running(record.id)
        project = self.projects.get(record.project_id)
        root = (self.projects.workspace_root / project.project_dir).resolve()
        context = PersistentRenderExecutionContext(
            job_id=record.id,
            project_dir=root,
            repository=self.repository,
            input_fingerprint=record.input_fingerprint,
            job_type=record.job_type,
        )
        self._audit(record.project_id, "video_render_job_started", {"job_id": str(record.id)})
        self.repository.record_attempt(record.id)
        try:
            if record.payload.get("render_generation") == "v2":
                if self.graph_exporter is None:
                    raise GraphExportError("RenderGraph V2 exporter is not configured")
                graph_id = str(record.payload.get("graph_id", ""))
                graph_hash = str(record.payload.get("graph_hash", ""))
                if not graph_id or not graph_hash:
                    raise GraphExportError("RenderGraph V2 job is missing graph identity")
                graph = RenderGraphSnapshotStore(root).load(graph_id)
                if graph.graph_hash != graph_hash:
                    raise GraphExportError("RenderGraph V2 snapshot hash changed")
                result = self.graph_exporter(record.project_id, graph, context)
            else:
                raw_props = record.payload.get("props")
                try:
                    props = (
                        ProjectVideoProps.model_validate(raw_props)
                        if isinstance(raw_props, dict)
                        else None
                    )
                except ValueError:
                    # Jobs created before output-profile freezing have no
                    # complete props payload.  Keep their legacy handler
                    # semantics instead of guessing a profile at execution.
                    props = None
                if props is None:
                    result = self.exporter.export(record.project_id, context=context)
                else:
                    result = self.exporter.export(
                        record.project_id,
                        context=context,
                        props_override=props,
                    )
        except RenderPauseRequested:
            self._audit(record.project_id, "video_render_job_paused", {"job_id": str(record.id)})
            return
        except RenderCancelled:
            if self.repository.get(record.id).status is JobStatus.CANCEL_REQUESTED:
                self.repository.cancel(record.id)
            self._audit(record.project_id, "video_render_job_cancelled", {"job_id": str(record.id)})
            return
        except Exception as error:
            code = _error_code(error)
            self.repository.fail(record.id, redact_text(str(error))[:500], code)
            self._audit(
                record.project_id,
                "video_render_job_failed",
                {"job_id": str(record.id), "error_code": code},
            )
            return
        payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)
        self.repository.succeed(record.id, payload)
        self._audit(record.project_id, "video_render_job_succeeded", {"job_id": str(record.id)})

    def _published_result_is_valid(self, project: Any, record: JobRecord) -> bool:
        result = record.result
        if not isinstance(result, dict):
            return False
        if record.payload.get("render_generation") == "v2" and result.get(
            "graph_hash"
        ) != record.payload.get("graph_hash"):
            return False
        root = (self.projects.workspace_root / project.project_dir).resolve()
        mp4 = self._safe_result_path(root, result.get("mp4_relative_path"))
        package = self._safe_result_path(root, result.get("package_relative_path"))
        if mp4 is None or not mp4.is_file() or mp4.stat().st_size <= 0:
            return False
        if package is None or not package.is_dir():
            return False
        manifest_path = package / "制作包清单.json"
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            artifacts = manifest["artifacts"]
        except (OSError, ValueError, KeyError, TypeError):
            return False
        if not isinstance(artifacts, list) or not artifacts:
            return False
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                return False
            path = self._safe_result_path(package, artifact.get("relative_path"))
            if path is None or not path.is_file():
                return False
            try:
                expected_size = int(artifact["size"])
                expected_hash = str(artifact["sha256"])
            except (KeyError, TypeError, ValueError):
                return False
            if path.stat().st_size != expected_size or self._sha256(path) != expected_hash:
                return False
        return True

    @staticmethod
    def _safe_result_path(root: Path, relative_path: object) -> Path | None:
        if not isinstance(relative_path, str) or not relative_path:
            return None
        candidate = (root / relative_path).resolve()
        if candidate == root or root not in candidate.parents:
            return None
        return candidate

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _write_input_snapshot(self, project: Any, record: JobRecord, props: Any) -> None:
        root = (self.projects.workspace_root / project.project_dir).resolve()
        snapshot = root / "09_日志" / "render-jobs" / str(record.id) / "input.json"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        content = (
            props.model_dump_json(indent=2)
            if hasattr(props, "model_dump_json")
            else json.dumps(props.model_dump(mode="json"), ensure_ascii=False, indent=2)
        )
        temporary = snapshot.with_name(".input.json.tmp")
        temporary.write_text(content + "\n", encoding="utf-8")
        temporary.replace(snapshot)

    @staticmethod
    def _write_graph_input_snapshot(root: Path, record: JobRecord, graph: RenderGraphV2) -> None:
        snapshot = root / "09_日志" / "render-jobs" / str(record.id) / "render-graph.json"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        temporary = snapshot.with_name(".render-graph.json.tmp")
        temporary.write_text(graph.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(snapshot)

    def _audit(self, project_id: UUID, action: str, details: dict[str, object]) -> None:
        try:
            project = self.projects.get(project_id)
            if hasattr(project, "model_copy"):
                self.projects.save(
                    project.model_copy(
                        update={
                            "audit_log": [
                                *project.audit_log,
                                AuditEvent(
                                    action=action, occurred_at=datetime.now(UTC), details=details
                                ),
                            ]
                        }
                    )
                )
        except Exception:
            pass


def _error_code(error: Exception) -> str:
    for error_type, code in ERROR_CODE_BY_EXCEPTION.items():
        if isinstance(error, error_type):
            return code
    return "video_export_rejected"
