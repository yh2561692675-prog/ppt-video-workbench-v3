"""Isolated, real-media S50 package and checkpoint-recovery acceptance."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import wave
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from PIL import Image

from workbench.audio.models import Transcript, TranscriptWord
from workbench.domain.confirmation import Confirmation
from workbench.domain.enums import JobStatus, JobType, NodeStatus
from workbench.domain.extraction import PageExtraction
from workbench.domain.models import AudioRecord, JobRecord, NarrationRecord, PageRecord
from workbench.jobs.checkpoint import Checkpoint
from workbench.jobs.execution import PersistentRenderExecutionContext, RenderExecutionContext
from workbench.jobs.repository import JobSpec
from workbench.main import create_app
from workbench.performance.sampler import PerformanceSampler
from workbench.video.models import ProjectVideoProps, VideoPageProps
from workbench.video.package_service import PackageManifest, VideoExportResult

_SCHEMA_VERSION = "1.0"
_PAGE_COUNT = 50
_PAGE_DURATION_MS = 300
_INTERRUPT_AFTER_PAGE = 10
_PROJECT_NAME = "s"
_WINDOWS_ACCEPTANCE_PATH_LIMIT = 240


class ControlledInterruption(BaseException):
    """Models a lost worker after a persisted page checkpoint."""


@dataclass(frozen=True, slots=True)
class S50Fixture:
    project_id: UUID
    project_root: Path
    page_count: int
    duration_ms: int
    source_manifest_sha256: str


class FfmpegPageRenderer:
    """Render deterministic fixture pages through the configured local FFmpeg."""

    def __init__(self, ffmpeg: str) -> None:
        self.ffmpeg = ffmpeg

    def render(
        self,
        props: ProjectVideoProps,
        page: VideoPageProps,
        source: Path,
        output: Path,
        control: object | None = None,
    ) -> None:
        del control
        output.parent.mkdir(parents=True, exist_ok=True)
        duration_seconds = (page.end_ms - page.start_ms) / 1_000
        result = subprocess.run(
            [
                self.ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-loop",
                "1",
                "-framerate",
                str(props.fps),
                "-i",
                str(source),
                "-t",
                f"{duration_seconds:.3f}",
                "-vf",
                f"scale={props.width}:{props.height}:flags=lanczos,format=yuv420p",
                "-r",
                str(props.fps),
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-pix_fmt",
                "yuv420p",
                str(output),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            raise RuntimeError(f"fixture FFmpeg page render failed: {result.returncode}")


class InterruptAfterPageCheckpoint:
    """Forward persistent execution calls and interrupt after a chosen page."""

    def __init__(self, delegate: RenderExecutionContext, page_order: int) -> None:
        self.delegate = delegate
        self.page_order = page_order
        self.interrupted = False

    @property
    def job_id(self) -> UUID | None:
        return self.delegate.job_id

    @property
    def input_fingerprint(self) -> str | None:
        return self.delegate.input_fingerprint

    @property
    def cancel_requested(self) -> bool:
        return self.delegate.cancel_requested

    def checkpoint(
        self,
        *,
        stage: str,
        progress: float,
        message: str,
        artifacts: Iterable[Path] = (),
        payload: Mapping[str, object] | None = None,
    ) -> None:
        self.delegate.checkpoint(
            stage=stage,
            progress=progress,
            message=message,
            artifacts=artifacts,
            payload=payload,
        )
        completed_raw = payload.get("completed_pages", []) if payload is not None else []
        completed = completed_raw if isinstance(completed_raw, list) else []
        if not self.interrupted and self.page_order in completed:
            self.interrupted = True
            raise ControlledInterruption()

    def raise_if_cancelled(self) -> None:
        self.delegate.raise_if_cancelled()

    def pause_if_requested(self) -> None:
        self.delegate.pause_if_requested()

    def heartbeat(self) -> None:
        self.delegate.heartbeat()

    def register_temporary_paths(self, paths: Iterable[Path]) -> None:
        self.delegate.register_temporary_paths(paths)


class StageSamplingContext:
    """Mirror durable checkpoints to the sampler without changing job semantics."""

    def __init__(self, delegate: RenderExecutionContext, sampler: PerformanceSampler) -> None:
        self.delegate = delegate
        self.sampler = sampler

    @property
    def job_id(self) -> UUID | None:
        return self.delegate.job_id

    @property
    def input_fingerprint(self) -> str | None:
        return self.delegate.input_fingerprint

    @property
    def cancel_requested(self) -> bool:
        return self.delegate.cancel_requested

    def checkpoint(
        self,
        *,
        stage: str,
        progress: float,
        message: str,
        artifacts: Iterable[Path] = (),
        payload: Mapping[str, object] | None = None,
    ) -> None:
        self.delegate.checkpoint(
            stage=stage,
            progress=progress,
            message=message,
            artifacts=artifacts,
            payload=payload,
        )
        if stage == "muxing":
            self.sampler.record_stage("page_render", "finished")
            self.sampler.record_stage("mux", "started")
        elif stage == "packaging":
            self.sampler.record_stage("mux", "finished")
            self.sampler.record_stage("package", "started")

    def raise_if_cancelled(self) -> None:
        self.delegate.raise_if_cancelled()

    def pause_if_requested(self) -> None:
        self.delegate.pause_if_requested()

    def heartbeat(self) -> None:
        self.delegate.heartbeat()

    def register_temporary_paths(self, paths: Iterable[Path]) -> None:
        self.delegate.register_temporary_paths(paths)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True, slots=True)
class S50RuntimeReport:
    fixture: S50Fixture
    job: JobRecord
    result: VideoExportResult
    checkpoint: Checkpoint
    package: dict[str, object]
    duration_ms: int
    project_root: Path
    checkpoint_count: int
    temporary_file_count: int


def execute_s50_acceptance(
    run_root: Path,
    *,
    ffmpeg: str,
    ffprobe: str,
) -> S50RuntimeReport:
    """Run the complete fixture through real FFmpeg and a forced checkpoint recovery."""

    run_root = run_root.resolve()
    if run_root.exists():
        raise FileExistsError(f"S50 run root already exists: {run_root}")
    _require_windows_path_budget(run_root)
    run_root.mkdir(parents=True)
    workspace = run_root / "w"
    # ProjectService intentionally does not create an arbitrary configured
    # workspace. This acceptance owns its candidate-specific directory, so it
    # must create that exact directory before asking the product store to
    # publish a project manifest.
    workspace.mkdir()
    sampler = PerformanceSampler(
        run_root / "performance",
        {"s50_harness": os.getpid()},
        temporary_root=run_root,
        interval_seconds=1.0,
    )
    sampler.start()
    sampler.record_stage("import", "started")
    started = time.perf_counter()
    try:
        app = create_app(workspace, video_renderer=FfmpegPageRenderer(ffmpeg))
        exporter = app.state.video_export_service
        exporter.ffmpeg = ffmpeg
        exporter.ffprobe = ffprobe
        fixture = _create_s50_fixture(app.state.project_service, run_root)
        sampler.record_stage("import", "finished")
        sampler.record_stage("preflight", "started")
        subtitle_service = exporter.preview.subtitles
        subtitle_service.build(fixture.project_id)
        preflight = exporter.preview.preflight(fixture.project_id)
        if not preflight.allowed:
            raise RuntimeError("S50 fixture preflight was blocked")
        sampler.record_stage("preflight", "finished")

        repository = app.state.project_service.jobs
        job = repository.enqueue_or_get(
            JobSpec(
                project_id=fixture.project_id,
                job_type=JobType.EXPORT_PACKAGE,
                cache_key=f"s50-{fixture.source_manifest_sha256}",
                input_fingerprint=None,
            )
        ).record
        if repository.claim_next(JobType.EXPORT_PACKAGE) is None:
            raise RuntimeError("S50 export job could not be claimed")
        project_root = fixture.project_root
        first_context = PersistentRenderExecutionContext(
            job_id=job.id,
            project_dir=project_root,
            repository=repository,
            input_fingerprint=None,
        )
        interrupted_context = InterruptAfterPageCheckpoint(
            StageSamplingContext(first_context, sampler), _INTERRUPT_AFTER_PAGE
        )
        sampler.record_stage("page_render", "started")
        try:
            exporter.export(fixture.project_id, context=interrupted_context)
        except ControlledInterruption:
            pass
        else:
            raise RuntimeError("S50 interruption injection did not fire")
        sampler.record_stage("page_render", "checkpoint")

        repository.recover_interrupted_jobs()
        paused = repository.get(job.id)
        if paused.status is not JobStatus.PAUSED:
            raise RuntimeError("interrupted S50 job was not made resumable")
        checkpoint = PersistentRenderExecutionContext(
            job_id=job.id,
            project_dir=project_root,
            repository=repository,
            input_fingerprint=None,
        ).restore()
        if checkpoint is None:
            raise RuntimeError("interrupted S50 job has no verified checkpoint")
        completed = checkpoint.payload.get("completed_pages")
        if not isinstance(completed, list) or _INTERRUPT_AFTER_PAGE not in completed:
            raise RuntimeError("S50 checkpoint did not retain interrupted-page progress")
        resumed = repository.resume(job.id)
        if resumed.id != job.id or repository.claim_next(JobType.EXPORT_PACKAGE) is None:
            raise RuntimeError("S50 export job could not resume")

        recovery_context = StageSamplingContext(
            PersistentRenderExecutionContext(
                job_id=job.id,
                project_dir=project_root,
                repository=repository,
                input_fingerprint=None,
            ),
            sampler,
        )
        result = exporter.export(fixture.project_id, context=recovery_context)
        package = _validate_package(project_root, result)
        sampler.record_stage("package", "finished")
        duration_ms = round((time.perf_counter() - started) * 1_000)
        return S50RuntimeReport(
            fixture=fixture,
            job=job,
            result=result,
            checkpoint=checkpoint,
            package=package,
            duration_ms=duration_ms,
            project_root=project_root,
            checkpoint_count=len(repository.list_checkpoints(job.id)),
            temporary_file_count=_temporary_file_count(run_root),
        )
    finally:
        summary = sampler.stop()
        _write_new_json(run_root / "s50-runtime-summary.json", {"summary": str(summary)})

def run_s50_acceptance(
    *,
    repo_root: Path,
    candidate: dict[str, object],
    candidate_manifest_path: Path,
    output_root: Path,
    ffmpeg: str,
    ffprobe: str,
) -> Path:
    """Publish non-overwriteable S50 evidence under ignored test-results only."""

    repo_root = repo_root.resolve()
    output_root = output_root.resolve()
    _require_test_results_child(repo_root, output_root)
    candidate_id, source_commit = _candidate_identity(candidate)
    manifest_sha256 = sha256_file(candidate_manifest_path)
    run_id = f"r-{time.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    # The full candidate ID remains in signed evidence.  Windows project
    # manifests also create an atomic temporary filename, so nesting the full
    # candidate ID here can exceed MAX_PATH before a render begins. A manifest
    # hash prefix is still candidate-specific while keeping every runtime path
    # below the Windows compatibility boundary.
    run_root = _candidate_run_root(output_root, manifest_sha256, run_id)
    report = execute_s50_acceptance(run_root, ffmpeg=ffmpeg, ffprobe=ffprobe)
    performance_summary = next((run_root / "performance").glob("*-summary.json"), None)
    performance_events = next((run_root / "performance").glob("*.jsonl"), None)
    if performance_summary is None or performance_events is None:
        raise RuntimeError("S50 sampler evidence is missing")
    evidence_path = run_root / "s50-acceptance-v1.json"
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "status": "passed",
        "run_id": run_id,
        "candidate": {
            "candidate_id": candidate_id,
            "source_commit": source_commit,
            "manifest_sha256": manifest_sha256,
        },
        "fixture": {
            "id": "S50-synthetic-media-v1",
            "page_count": report.fixture.page_count,
            "page_duration_ms": _PAGE_DURATION_MS,
            "duration_ms": report.fixture.duration_ms,
            "source_manifest_sha256": report.fixture.source_manifest_sha256,
            "content_policy": "generated image plus generated WAV only",
        },
        "recovery": {
            "interruption_after_page": _INTERRUPT_AFTER_PAGE,
            "checkpoint_completed_pages": report.checkpoint.payload.get("completed_pages"),
            "checkpoint_count": report.checkpoint_count,
            "result_cached_pages_after_resume": report.result.cached_pages,
            "job_id": str(report.job.id),
        },
        "result": {
            "elapsed_ms": report.duration_ms,
            "mp4_relative_path": report.result.mp4_relative_path,
            "package_relative_path": report.result.package_relative_path,
            "duration_ms": report.result.duration_ms,
            "video_codec": report.result.video_codec,
            "audio_codec": report.result.audio_codec,
            "artifact_count": report.result.artifact_count,
            "temporary_file_count_at_completion": report.temporary_file_count,
            **report.package,
        },
        "performance": {
            "summary_path": str(performance_summary),
            "summary_sha256": sha256_file(performance_summary),
            "events_path": str(performance_events),
            "events_sha256": sha256_file(performance_events),
        },
        "scope": {
            "executed": (
                "local FFmpeg pages, page mux, final concat, subtitles and production package"
            ),
            "not_executed": [
                "real external provider",
                "Remotion browser renderer",
                "cloud executor",
                "human-presenter source",
            ],
        },
    }
    _write_new_json(evidence_path, payload)
    return evidence_path


def _create_s50_fixture(projects: Any, run_root: Path) -> S50Fixture:
    del run_root
    # Keep the generated ProjectService directory short. Its atomic manifest
    # writer appends a UUID temporary filename during every checkpoint update.
    project = projects.create(_PROJECT_NAME)
    project_root = (projects.workspace_root / project.project_dir).resolve()
    pages: list[PageRecord] = []
    extractions: list[PageExtraction] = []
    confirmations: list[Confirmation] = []
    words: list[TranscriptWord] = []
    manifest_rows: list[dict[str, object]] = []
    for page_order in range(1, _PAGE_COUNT + 1):
        page_id = uuid4()
        revision_id = uuid4()
        image = project_root / "02_pages" / f"page-{page_order:04d}.png"
        audio = project_root / "05_audio" / f"page-{page_order:04d}.wav"
        _write_page_image(image, page_order)
        _write_wav(audio, _PAGE_DURATION_MS, page_order=page_order)
        relative_audio = audio.relative_to(project_root).as_posix()
        start_ms = (page_order - 1) * _PAGE_DURATION_MS
        end_ms = page_order * _PAGE_DURATION_MS
        pages.append(
            PageRecord(
                id=page_id,
                order=page_order,
                title=f"S50 page {page_order}",
                narration=NarrationRecord(
                    id=uuid4(),
                    revision_id=revision_id,
                    confirmed_revision_id=revision_id,
                    text=f"Synthetic S50 narration page {page_order}.",
                    status=NodeStatus.COMPLETED,
                    author="performance-fixture",
                ),
                audio=AudioRecord(
                    id=uuid4(),
                    status=NodeStatus.COMPLETED,
                    source="heygen",
                    relative_path=relative_audio,
                    duration_ms=_PAGE_DURATION_MS,
                    cache_key=sha256_file(audio),
                    narration_revision_id=revision_id,
                    voice_id="synthetic-local-fixture",
                ),
            )
        )
        confirmations.append(
            Confirmation(
                id=uuid4(),
                page_id=page_id,
                revision_id=revision_id,
                actor="performance-fixture",
                confirmed_at=datetime.now(UTC),
            )
        )
        extractions.append(
            PageExtraction(
                id=uuid4(),
                order=page_order,
                title=f"S50 page {page_order}",
                preview_path=image,
                extraction_method="image",
                source_ref="S50-synthetic-media-v1",
            )
        )
        words.append(
            TranscriptWord(
                text=f"Page {page_order}",
                start_ms=start_ms + 10,
                end_ms=end_ms - 10,
                confidence=1.0,
            )
        )
        manifest_rows.append(
            {
                "page_order": page_order,
                "image_sha256": sha256_file(image),
                "audio_sha256": sha256_file(audio),
            }
        )
    canonical = json.dumps(manifest_rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    source_manifest_sha256 = hashlib.sha256(canonical).hexdigest()
    projects.save(
        project.model_copy(
            update={
                "pages": pages,
                "page_extractions": extractions,
                "narration_confirmations": confirmations,
                "transcript": Transcript(
                    words=words,
                    detected_language="en",
                    model="synthetic-s50-fixture",
                    device="cpu",
                    created_at=datetime.now(UTC),
                ),
            }
        )
    )
    return S50Fixture(
        project_id=project.id,
        project_root=project_root,
        page_count=_PAGE_COUNT,
        duration_ms=_PAGE_COUNT * _PAGE_DURATION_MS,
        source_manifest_sha256=source_manifest_sha256,
    )


def _write_page_image(path: Path, page_order: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    color = (page_order * 31 % 256, page_order * 61 % 256, page_order * 97 % 256)
    Image.new("RGB", (640, 360), color).save(path, format="PNG")


def _write_wav(path: Path, duration_ms: int, *, page_order: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = 16_000 * duration_ms // 1_000
    # A per-page value makes the generated media and its cache key unique.
    # Identical silence would correctly be rejected by the product audio gate
    # as accidental reuse across pages.
    sample = page_order.to_bytes(2, byteorder="little", signed=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(sample * frame_count)


def _validate_package(project_root: Path, result: VideoExportResult) -> dict[str, object]:
    mp4 = (project_root / result.mp4_relative_path).resolve()
    package_root = (project_root / result.package_relative_path).resolve()
    if not mp4.is_file() or not package_root.is_dir():
        raise RuntimeError("S50 final MP4 or package was not published")
    srt = next(package_root.rglob("*.srt"), None)
    package_manifest_path = next(
        (
            path
            for path in package_root.rglob("*.json")
            if _is_package_manifest(path)
        ),
        None,
    )
    if srt is None or package_manifest_path is None:
        raise RuntimeError("S50 package is missing SRT or artifact manifest")
    manifest = PackageManifest.model_validate_json(
        package_manifest_path.read_text(encoding="utf-8")
    )
    for artifact in manifest.artifacts:
        path = (package_root / artifact.relative_path).resolve()
        if package_root not in path.parents or not path.is_file():
            raise RuntimeError("S50 package manifest references a missing artifact")
        if path.stat().st_size != artifact.size or sha256_file(path) != artifact.sha256:
            raise RuntimeError("S50 package manifest artifact hash mismatch")
    return {
        "final_mp4_sha256": sha256_file(mp4),
        "final_mp4_size_bytes": mp4.stat().st_size,
        "srt_sha256": sha256_file(srt),
        "package_manifest_sha256": sha256_file(package_manifest_path),
        "package_manifest_artifact_count": len(manifest.artifacts),
    }


def _is_package_manifest(path: Path) -> bool:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        isinstance(raw, dict)
        and raw.get("version") == 1
        and isinstance(raw.get("artifacts"), list)
    )


def _candidate_identity(candidate: dict[str, object]) -> tuple[str, str]:
    candidate_id = candidate.get("candidate_id")
    source = candidate.get("source")
    if not isinstance(candidate_id, str) or not isinstance(source, dict):
        raise ValueError("validated candidate manifest is incomplete")
    source_commit = source.get("commit")
    if not isinstance(source_commit, str):
        raise ValueError("validated candidate source commit is missing")
    return candidate_id, source_commit


def _candidate_run_root(output_root: Path, manifest_sha256: str, run_id: str) -> Path:
    if len(manifest_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in manifest_sha256
    ):
        raise ValueError("candidate manifest SHA-256 must be a lowercase 64-character digest")
    if not run_id.startswith("r-"):
        raise ValueError("S50 run ID is invalid")
    return output_root / f"c-{manifest_sha256[:12]}" / run_id


def _require_windows_path_budget(run_root: Path) -> None:
    """Reject an S50 evidence layout that cannot publish the deepest package file."""

    projected = (
        run_root
        / "w"
        / "s_20260813_0102"
        / "08_输出"
        / ".render-jobs"
        / ("0" * 8 + "-" + "0" * 4 + "-" + "0" * 4 + "-" + "0" * 4 + "-" + "0" * 12)
        / "制作包"
        / "Remotion工程"
        / "ProjectVideoProps.json"
    )
    if os.name == "nt" and len(str(projected)) >= _WINDOWS_ACCEPTANCE_PATH_LIMIT:
        raise ValueError(
            "S50 acceptance output root is too deep for Windows package publication; "
            "choose a shorter path inside test-results"
        )


def _require_test_results_child(repo_root: Path, output_root: Path) -> None:
    allowed_root = (repo_root / "test-results").resolve()
    try:
        output_root.relative_to(allowed_root)
    except ValueError as error:
        raise ValueError("output_root must remain inside repository test-results") from error


def _temporary_file_count(root: Path) -> int:
    return sum(
        1
        for path in root.rglob("*")
        if path.is_file() and path.suffix == ".tmp"
    )


def _write_new_json(path: Path, value: object) -> None:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(serialized)
