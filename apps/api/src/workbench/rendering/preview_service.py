from __future__ import annotations

import shutil
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from workbench.cache.contracts import CacheDomain
from workbench.cache.models import PersistentCacheEntry
from workbench.cache.persistent_repository import PersistentCacheRepository
from workbench.domain.enums import JobType
from workbench.domain.models import JobRecord
from workbench.jobs.execution import PersistentRenderExecutionContext
from workbench.jobs.repository import JobRepository, JobSpec
from workbench.media.probe import MediaProbeResult, probe_media
from workbench.rendering.export_pipeline import RenderGraphExportPipeline
from workbench.rendering.hashing import sha256_file, sha256_json
from workbench.rendering.models import RenderGraphV2
from workbench.rendering.preflight import GraphPreflight, GraphPreflightReport
from workbench.rendering.preview import (
    RenderGraphPreviewPlan,
    RenderGraphPreviewRequest,
    build_preview_plan,
)
from workbench.rendering.range_projection import project_render_range
from workbench.rendering.snapshot_store import RenderGraphSnapshotStore
from workbench.services.project_service import ProjectService


class PreviewSubmissionBlocked(ValueError):
    def __init__(self, report: GraphPreflightReport) -> None:
        super().__init__("authoritative preview preflight failed")
        self.report = report


class AuthoritativePreviewJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    graph_id: UUID
    graph_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    runtime_version: str = Field(default="rendergraph-v2", min_length=1, max_length=80)
    priority: int = Field(default=100, ge=-100, le=100)
    client_request_id: str | None = Field(default=None, min_length=1, max_length=120)


class PreviewArtifactManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    project_id: UUID
    job_id: UUID
    graph_id: UUID
    graph_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    projected_graph_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    duration_us: int = Field(gt=0)
    timeline_revision: int = Field(ge=0)
    runtime_version: str = Field(min_length=1, max_length=80)
    subtitle_mode: str = Field(min_length=1, max_length=40)
    cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    video_relative_path: str = Field(min_length=1, max_length=500)
    video_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0)
    container: str = Field(min_length=1, max_length=200)
    probe_tool_version: str = Field(min_length=1, max_length=200)
    has_audio: bool


PreviewExecutor = Callable[
    [RenderGraphV2, Path, PersistentRenderExecutionContext], Path
]
PreviewProbe = Callable[[Path], MediaProbeResult]


class AuthoritativePreviewService:
    def __init__(
        self,
        projects: ProjectService,
        *,
        repository: JobRepository | None = None,
        executor: PreviewExecutor | None = None,
        artifact_probe: PreviewProbe | None = None,
        cache: PersistentCacheRepository | None = None,
    ) -> None:
        self.projects = projects
        self.repository = repository or projects.jobs
        self.executor = executor or self._default_executor
        self.artifact_probe = artifact_probe or probe_media
        self.cache = cache or PersistentCacheRepository(
            projects.database, projects.workspace_root
        )

    def submit(
        self, project_id: UUID, request: AuthoritativePreviewJobRequest
    ) -> JobRecord:
        root = self._project_root(project_id)
        graph = RenderGraphSnapshotStore(root).load(str(request.graph_id))
        if graph.project_id != project_id or graph.graph_hash != request.graph_hash:
            raise ValueError("preview graph id/hash does not match the project snapshot")
        preview_request = RenderGraphPreviewRequest(
            start_us=request.start_us,
            end_us=request.end_us,
            preset="authoritative",
            runtime_version=request.runtime_version,
        )
        plan = build_preview_plan(graph, preview_request)
        report = GraphPreflight().check(graph, root)
        if not report.allowed:
            raise PreviewSubmissionBlocked(report)
        projection = project_render_range(graph, plan.start_us, plan.end_us)
        cached_video = root / "07_视频工程" / "preview-cache" / plan.cache_key / "preview.mp4"
        indexed = self.cache.lookup(
            plan.cache_key, runtime_fingerprint=plan.runtime_version
        )
        reuse_succeeded = indexed.hit and self._valid_probe(cached_video, projection) is not None
        return self.repository.enqueue_or_get(
            JobSpec(
                project_id=project_id,
                job_type=JobType.RENDER_PREVIEW,
                cache_key=f"authoritative-preview:{plan.cache_key}",
                input_fingerprint=plan.cache_key,
                priority=request.priority,
                payload={
                    "plan": plan.model_dump(mode="json"),
                    "client_request_id": request.client_request_id,
                },
            ),
            reuse_succeeded=reuse_succeeded,
        ).record

    def handle(self, job: JobRecord) -> None:
        plan = RenderGraphPreviewPlan.model_validate(job.payload.get("plan"))
        root = self._project_root(job.project_id)
        graph = RenderGraphSnapshotStore(root).load(plan.graph_id)
        if graph.graph_hash != plan.graph_hash:
            raise ValueError("preview graph snapshot hash changed")
        projection = project_render_range(graph, plan.start_us, plan.end_us)
        context = PersistentRenderExecutionContext(
            job_id=job.id,
            project_dir=root,
            repository=self.repository,
            input_fingerprint=job.input_fingerprint,
            job_type=JobType.RENDER_PREVIEW,
        )
        context.checkpoint(
            stage="projected",
            progress=0.1,
            message="authoritative preview range projected",
            payload={"projected_graph_hash": projection.graph_hash},
        )
        cache_root = root / "07_视频工程" / "preview-cache" / plan.cache_key
        video = cache_root / "preview.mp4"
        probe = self._valid_probe(video, projection)
        if probe is None:
            temporary = root / "07_视频工程" / ".preview-jobs" / str(job.id)
            if temporary.exists():
                shutil.rmtree(temporary)
            rendered = self.executor(projection, temporary, context)
            if not rendered.is_file() or rendered.stat().st_size <= 0:
                raise ValueError("authoritative preview executor produced no video")
            probe = self._valid_probe(rendered, projection)
            if probe is None:
                raise ValueError("authoritative preview artifact failed media validation")
            canonical_video = temporary / "preview.mp4"
            if rendered != canonical_video:
                rendered.replace(canonical_video)
                rendered = canonical_video
            cache_root.parent.mkdir(parents=True, exist_ok=True)
            if cache_root.exists():
                shutil.rmtree(cache_root)
            temporary.replace(cache_root)
            video = cache_root / rendered.relative_to(temporary)
        context.checkpoint(
            stage="published",
            progress=0.9,
            message="authoritative preview published",
            artifacts=[video],
        )
        manifest = PreviewArtifactManifestV1(
            project_id=job.project_id,
            job_id=job.id,
            graph_id=UUID(plan.graph_id),
            graph_hash=plan.graph_hash,
            projected_graph_hash=projection.graph_hash,
            start_us=plan.start_us,
            end_us=plan.end_us,
            duration_us=projection.duration_us,
            timeline_revision=projection.timeline_revision,
            runtime_version=plan.runtime_version,
            subtitle_mode=projection.subtitles.render_mode,
            cache_key=plan.cache_key,
            video_relative_path=video.relative_to(root).as_posix(),
            video_hash=sha256_file(video),
            size_bytes=video.stat().st_size,
            container=probe.container,
            probe_tool_version=probe.tool_version,
            has_audio=any(stream.kind == "audio" for stream in probe.streams),
        )
        manifest_payload = manifest.model_dump(mode="json")
        self.cache.put(
            PersistentCacheEntry(
                cache_key=plan.cache_key,
                project_id=job.project_id,
                domain=CacheDomain.FINAL,
                node_key=f"authoritative-preview:{plan.start_us}:{plan.end_us}",
                artifact_manifest=manifest_payload,
                artifact_manifest_hash=sha256_json(manifest_payload),
                relative_path=video.relative_to(self.projects.workspace_root).as_posix(),
                artifact_hash=manifest.video_hash,
                size_bytes=manifest.size_bytes,
                runtime_fingerprint=plan.runtime_version,
                license_status="confirmed",
                dependencies=tuple(projection.cache_dependencies),
            )
        )
        attempt = self.repository.current_attempt(job.id)
        if attempt is None:
            raise ValueError("preview job has no active attempt")
        publication = self.repository.reserve_publication(
            f"preview:{job.project_id}:{plan.cache_key}",
            job.id,
            attempt.id,
            manifest_payload,
        )
        self.repository.publish_publication(
            publication.publication_key,
            job_id=job.id,
            attempt_id=attempt.id,
            manifest_hash=publication.manifest_hash,
        )
        self.repository.succeed(job.id, {"manifest": manifest_payload})

    def _project_root(self, project_id: UUID) -> Path:
        project = self.projects.get(project_id)
        return (self.projects.workspace_root / project.project_dir).resolve()

    def _valid_probe(
        self, video: Path, graph: RenderGraphV2
    ) -> MediaProbeResult | None:
        try:
            if not video.is_file() or video.stat().st_size <= 0:
                return None
            result = self.artifact_probe(video)
        except (OSError, RuntimeError, ValueError):
            return None
        video_stream = next(
            (stream for stream in result.streams if stream.kind == "video"), None
        )
        if video_stream is None or not any(
            stream.kind == "audio" for stream in result.streams
        ):
            return None
        if graph.canvas.fps_num is None or graph.canvas.fps_den is None:
            return None
        fps = Fraction(graph.canvas.fps_num, graph.canvas.fps_den)
        actual_fps = (
            Fraction(video_stream.fps_num, video_stream.fps_den)
            if video_stream.fps_num is not None and video_stream.fps_den is not None
            else None
        )
        frame_tolerance_us = (
            1_000_000 * fps.denominator + fps.numerator - 1
        ) // fps.numerator
        if (
            video_stream.width != graph.canvas.width
            or video_stream.height != graph.canvas.height
            or actual_fps != fps
            or abs(result.duration_us - graph.duration_us) > frame_tolerance_us
        ):
            return None
        return result

    @staticmethod
    def _default_executor(
        graph: RenderGraphV2,
        output_dir: Path,
        context: PersistentRenderExecutionContext,
    ) -> Path:
        result = RenderGraphExportPipeline(context.project_dir).export(
            graph,
            output_dir,
            context=context,
            execution_mode="authoritative-preview",
        )
        return result.video_path
