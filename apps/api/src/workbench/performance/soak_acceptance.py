"""Candidate-bound, real-media DP45 soak and recovery acceptance.

The runner is deliberately local and deterministic: every cycle uses the V1
``VideoExportService`` over generated pages and WAV assets, then samples the
actual Python/FFmpeg process tree.  Periodic cycles also simulate a worker
death after a persisted page checkpoint and a cancellation after a checkpoint,
so long-running evidence includes recovery and cleanup rather than only
successful exports.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import wave
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
from workbench.jobs.checkpoint import CheckpointStore
from workbench.jobs.execution import PersistentRenderExecutionContext, RenderExecutionContext
from workbench.jobs.repository import JobRepository, JobSpec
from workbench.main import create_app
from workbench.performance.s50_acceptance import FfmpegPageRenderer, _validate_package, sha256_file
from workbench.performance.sampler import (
    PerformanceSampler,
    ProcessObservation,
    SystemProcessProvider,
)
from workbench.video.fingerprint import render_input_fingerprint
from workbench.video.models import ProjectVideoProps
from workbench.video.package_service import VideoExportResult

_SCHEMA_VERSION = "1.0"
# The V1 concat path copies page streams.  A 300ms page is not an integral
# number of 24fps frames and produces a fractional final stream timebase after
# concat.  Use one-second fixture pages so this soak validates the qualified
# CFR delivery path instead of relying on a lossy rate rounding policy.
_DEFAULT_PAGE_DURATION_MS = 1_000
_WINDOWS_ACCEPTANCE_PATH_LIMIT = 240
_DEFAULT_LEDGER_SEGMENT_BYTES = 256 * 1024


class ControlledInterruption(BaseException):
    """Models loss of a worker immediately after its checkpoint is durable."""


@dataclass(frozen=True, slots=True)
class SoakFixture:
    project_id: UUID
    project_root: Path
    page_count: int
    duration_ms: int
    source_manifest_sha256: str


@dataclass(frozen=True, slots=True)
class SoakCycle:
    number: int
    mode: str
    elapsed_ms: int
    job_ids: tuple[str, ...]
    checkpoint_count: int
    cached_pages: int
    temporary_file_count: int
    package_sha256: str


@dataclass(frozen=True, slots=True)
class SoakRuntimeReport:
    fixture: SoakFixture
    cycles: tuple[SoakCycle, ...]
    started_monotonic: float
    finished_monotonic: float
    sampler_summary: Path
    sampler_events: Path
    ledger_paths: tuple[Path, ...]
    final_temporary_file_count: int
    orphan_processes: tuple[str, ...]
    pruned_successful_job_count: int


class _InterruptAfterPageCheckpoint:
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
        artifacts: tuple[Path, ...] = (),
        payload: dict[str, object] | None = None,
    ) -> None:
        self.delegate.checkpoint(
            stage=stage,
            progress=progress,
            message=message,
            artifacts=artifacts,
            payload=payload,
        )
        completed = payload.get("completed_pages", []) if payload is not None else []
        if not self.interrupted and isinstance(completed, list) and self.page_order in completed:
            self.interrupted = True
            raise ControlledInterruption()

    def raise_if_cancelled(self) -> None:
        self.delegate.raise_if_cancelled()

    def pause_if_requested(self) -> None:
        self.delegate.pause_if_requested()

    def heartbeat(self) -> None:
        self.delegate.heartbeat()

    def register_temporary_paths(self, paths: tuple[Path, ...]) -> None:
        self.delegate.register_temporary_paths(paths)


class _CancelAfterPageCheckpoint:
    def __init__(self, delegate: PersistentRenderExecutionContext, page_order: int) -> None:
        self.delegate = delegate
        self.page_order = page_order
        self.cancel_requested_once = False

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
        artifacts: tuple[Path, ...] = (),
        payload: dict[str, object] | None = None,
    ) -> None:
        self.delegate.checkpoint(
            stage=stage,
            progress=progress,
            message=message,
            artifacts=artifacts,
            payload=payload,
        )
        completed = payload.get("completed_pages", []) if payload is not None else []
        if (
            not self.cancel_requested_once
            and isinstance(completed, list)
            and self.page_order in completed
        ):
            self.cancel_requested_once = True
            self.delegate.repository.request_cancel(self.delegate.job_id)

    def raise_if_cancelled(self) -> None:
        self.delegate.raise_if_cancelled()

    def pause_if_requested(self) -> None:
        self.delegate.pause_if_requested()

    def heartbeat(self) -> None:
        self.delegate.heartbeat()

    def register_temporary_paths(self, paths: tuple[Path, ...]) -> None:
        self.delegate.register_temporary_paths(paths)


class _RotatingLedger:
    """Owned acceptance activity log with an explicit, bounded rotation policy."""

    def __init__(self, directory: Path, *, max_segment_bytes: int) -> None:
        if max_segment_bytes <= 0:
            raise ValueError("ledger segment size must be positive")
        self.directory = directory
        self.max_segment_bytes = max_segment_bytes
        self.directory.mkdir(parents=True, exist_ok=True)
        self._segment = 1
        self._paths: list[Path] = []

    @property
    def paths(self) -> tuple[Path, ...]:
        return tuple(self._paths)

    def append(self, event: dict[str, object]) -> None:
        path = self._current()
        serialized = json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n"
        encoded = serialized.encode("utf-8")
        if path.exists() and path.stat().st_size + len(encoded) > self.max_segment_bytes:
            self._segment += 1
            path = self._current()
        with path.open("ab") as handle:
            handle.write(encoded)

    def _current(self) -> Path:
        path = self.directory / f"soak-events-{self._segment:04d}.jsonl"
        if path not in self._paths:
            self._paths.append(path)
        return path


def execute_soak_acceptance(
    run_root: Path,
    *,
    ffmpeg: str,
    ffprobe: str,
    duration_seconds: float,
    minimum_cycles: int,
    cycle_interval_seconds: float,
    page_count: int,
    recovery_every: int,
    cancellation_every: int,
    retain_completed_jobs: int = 2,
    ledger_segment_bytes: int = _DEFAULT_LEDGER_SEGMENT_BYTES,
) -> SoakRuntimeReport:
    """Run real exports until duration and cycle minimum are both satisfied."""

    _validate_options(
        duration_seconds=duration_seconds,
        minimum_cycles=minimum_cycles,
        cycle_interval_seconds=cycle_interval_seconds,
        page_count=page_count,
        recovery_every=recovery_every,
        cancellation_every=cancellation_every,
        retain_completed_jobs=retain_completed_jobs,
    )
    run_root = run_root.resolve()
    if run_root.exists():
        raise FileExistsError(f"DP45 soak run root already exists: {run_root}")
    _require_windows_path_budget(run_root)
    run_root.mkdir(parents=True)
    workspace = run_root / "w"
    workspace.mkdir()
    app = create_app(workspace, video_renderer=FfmpegPageRenderer(ffmpeg))
    projects = app.state.project_service
    repository: JobRepository = projects.jobs
    exporter = app.state.video_export_service
    exporter.ffmpeg = ffmpeg
    exporter.ffprobe = ffprobe
    fixture = _create_fixture(projects, page_count=page_count)
    exporter.preview.subtitles.build(fixture.project_id)
    sampler = PerformanceSampler(
        run_root / "performance",
        {"soak_harness": os.getpid()},
        temporary_root=run_root,
        interval_seconds=1.0,
    )
    ledger = _RotatingLedger(run_root / "logs", max_segment_bytes=ledger_segment_bytes)
    started = time.monotonic()
    deadline = started + duration_seconds
    cycles: list[SoakCycle] = []
    completed_job_ids: list[str] = []
    pruned_successful_job_count = 0
    sampler.start()
    try:
        while time.monotonic() < deadline or len(cycles) < minimum_cycles:
            number = len(cycles) + 1
            mode = _cycle_mode(number, recovery_every, cancellation_every)
            sampler.record_stage("soak_cycle", "started")
            cycle_started = time.perf_counter()
            cycle = _execute_cycle(
                number=number,
                mode=mode,
                fixture=fixture,
                exporter=exporter,
                repository=repository,
            )
            elapsed_ms = round((time.perf_counter() - cycle_started) * 1_000)
            temporary = _temporary_file_count(fixture.project_root)
            if temporary != 0:
                raise RuntimeError(f"DP45 cycle {number} left unpublished temporary files")
            checked = SoakCycle(
                number=cycle.number,
                mode=cycle.mode,
                elapsed_ms=elapsed_ms,
                job_ids=cycle.job_ids,
                checkpoint_count=cycle.checkpoint_count,
                cached_pages=cycle.cached_pages,
                temporary_file_count=temporary,
                package_sha256=cycle.package_sha256,
            )
            cycles.append(checked)
            # A cancel/retry cycle contains the cancelled job followed by the
            # retry that actually published the validated package.  Retention
            # is deliberately limited to that final successful job so the
            # cancelled job's diagnostic history remains available.
            completed_job_ids.append(checked.job_ids[-1])
            retained_job_ids = completed_job_ids[-retain_completed_jobs:]
            pruned = _prune_completed_cycle_artifacts(
                fixture,
                completed_job_ids[:-retain_completed_jobs],
            )
            if pruned:
                pruned_successful_job_count += len(pruned)
                completed_job_ids = retained_job_ids
            ledger.append(
                {
                    "type": "cycle_finished",
                    "number": checked.number,
                    "mode": checked.mode,
                    "elapsed_ms": checked.elapsed_ms,
                    "job_ids": checked.job_ids,
                    "checkpoint_count": checked.checkpoint_count,
                    "cached_pages": checked.cached_pages,
                    "temporary_file_count": checked.temporary_file_count,
                    "package_sha256": checked.package_sha256,
                    "pruned_successful_job_ids": pruned,
                }
            )
            sampler.record_stage("soak_cycle", "finished")
            remaining = deadline - time.monotonic()
            if remaining > 0 and cycle_interval_seconds > 0:
                time.sleep(min(cycle_interval_seconds, remaining))
    finally:
        summary = sampler.stop()
    final_temporary = _temporary_file_count(fixture.project_root)
    if final_temporary != 0:
        raise RuntimeError("DP45 final project contains unpublished temporary files")
    orphans = _child_processes_of_current_harness()
    if orphans:
        raise RuntimeError(f"DP45 found remaining child media processes: {', '.join(orphans)}")
    _validate_job_hygiene(repository)
    _validate_ledger(ledger.paths, ledger_segment_bytes)
    return SoakRuntimeReport(
        fixture=fixture,
        cycles=tuple(cycles),
        started_monotonic=started,
        finished_monotonic=time.monotonic(),
        sampler_summary=summary,
        sampler_events=sampler.events_path,
        ledger_paths=ledger.paths,
        final_temporary_file_count=final_temporary,
        orphan_processes=tuple(orphans),
        pruned_successful_job_count=pruned_successful_job_count,
    )


def run_soak_acceptance(
    *,
    repo_root: Path,
    candidate: dict[str, object],
    candidate_manifest_path: Path,
    output_root: Path,
    ffmpeg: str,
    ffprobe: str,
    duration_seconds: float,
    minimum_cycles: int,
    cycle_interval_seconds: float,
    page_count: int,
    recovery_every: int,
    cancellation_every: int,
    retain_completed_jobs: int = 2,
    ledger_segment_bytes: int = _DEFAULT_LEDGER_SEGMENT_BYTES,
) -> Path:
    """Write non-overwriteable candidate-bound DP45 evidence under test-results."""

    repo_root = repo_root.resolve()
    output_root = output_root.resolve()
    _require_test_results_child(repo_root, output_root)
    candidate_id, source_commit = _candidate_identity(candidate)
    manifest_sha256 = sha256_file(candidate_manifest_path)
    run_id = f"r-soak-{time.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    run_root = _candidate_run_root(output_root, manifest_sha256, run_id)
    report = execute_soak_acceptance(
        run_root,
        ffmpeg=ffmpeg,
        ffprobe=ffprobe,
        duration_seconds=duration_seconds,
        minimum_cycles=minimum_cycles,
        cycle_interval_seconds=cycle_interval_seconds,
        page_count=page_count,
        recovery_every=recovery_every,
        cancellation_every=cancellation_every,
        retain_completed_jobs=retain_completed_jobs,
        ledger_segment_bytes=ledger_segment_bytes,
    )
    sampler_summary = _load_json(report.sampler_summary)
    sampler_events = _load_sampler_events(report.sampler_events)
    evidence_path = run_root / "soak-acceptance-v1.json"
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "status": "passed",
        "run_id": run_id,
        "candidate": {
            "candidate_id": candidate_id,
            "source_commit": source_commit,
            "manifest_sha256": manifest_sha256,
        },
        "requested": {
            "duration_seconds": duration_seconds,
            "minimum_cycles": minimum_cycles,
            "cycle_interval_seconds": cycle_interval_seconds,
            "page_count": page_count,
            "recovery_every": recovery_every,
            "cancellation_every": cancellation_every,
            "retain_completed_jobs": retain_completed_jobs,
        },
        "observed": {
            "duration_seconds": round(report.finished_monotonic - report.started_monotonic, 3),
            "cycle_count": len(report.cycles),
            "recovery_cycles": sum(cycle.mode == "recovery" for cycle in report.cycles),
            "cancel_retry_cycles": sum(cycle.mode == "cancel_retry" for cycle in report.cycles),
            "normal_cycles": sum(cycle.mode == "normal" for cycle in report.cycles),
            "final_temporary_file_count": report.final_temporary_file_count,
            "orphan_processes": list(report.orphan_processes),
            "pruned_successful_job_count": report.pruned_successful_job_count,
            "rss_curve": _rss_curve(sampler_events),
            "sampler": _sampler_payload(report.sampler_summary, sampler_summary),
            "ledger": {
                "paths": [path.relative_to(run_root).as_posix() for path in report.ledger_paths],
                "sha256": [sha256_file(path) for path in report.ledger_paths],
                "max_segment_bytes": ledger_segment_bytes,
            },
        },
        "fixture": {
            "id": "DP45-repeated-local-v1",
            "page_count": report.fixture.page_count,
            "duration_ms": report.fixture.duration_ms,
            "source_manifest_sha256": report.fixture.source_manifest_sha256,
            "content_policy": "generated image plus generated WAV only",
        },
        "cycles": [
            {
                "number": cycle.number,
                "mode": cycle.mode,
                "elapsed_ms": cycle.elapsed_ms,
                "job_ids": list(cycle.job_ids),
                "checkpoint_count": cycle.checkpoint_count,
                "cached_pages": cycle.cached_pages,
                "temporary_file_count": cycle.temporary_file_count,
                "package_sha256": cycle.package_sha256,
            }
            for cycle in report.cycles
        ],
        "boundary": {
            "completed": (
                "local repeated preview/export, checkpoint recovery, cancellation cleanup, "
                "retry, resource sampling and process hygiene"
            ),
            "not_claimed": [
                "real external provider",
                "hardware-specific GPU budget",
                "signed installer",
                "production application log rotation"
            ],
            "log_rotation_note": (
                "The acceptance owns and rotates its event ledger. The fixture does not claim "
                "production application logging where no app log emitter is exercised."
            ),
        },
    }
    _write_new_json(evidence_path, payload)
    return evidence_path


def _execute_cycle(
    *,
    number: int,
    mode: str,
    fixture: SoakFixture,
    exporter: Any,
    repository: JobRepository,
) -> SoakCycle:
    preflight = exporter.preview.preview(fixture.project_id)
    if not preflight.allowed or preflight.props is None:
        raise RuntimeError("DP45 fixture preview is blocked")
    props = preflight.props.model_copy(update={"width": 1280, "height": 720, "fps": 24})
    fingerprint = render_input_fingerprint(preflight.model_copy(update={"props": props}))
    if mode == "recovery":
        result, job_ids, checkpoints = _run_recovery_cycle(
            number, fixture, exporter, repository, props, fingerprint
        )
    elif mode == "cancel_retry":
        result, job_ids, checkpoints = _run_cancel_retry_cycle(
            number, fixture, exporter, repository, props, fingerprint
        )
    else:
        result, job_ids, checkpoints = _run_successful_export(
            number, fixture, exporter, repository, props, fingerprint, label="normal"
        )
    package = _validate_package(fixture.project_root, result)
    package_hash = package.get("package_manifest_sha256")
    if not isinstance(package_hash, str):
        raise RuntimeError("DP45 package validation did not return an artifact manifest hash")
    return SoakCycle(
        number=number,
        mode=mode,
        elapsed_ms=0,
        job_ids=job_ids,
        checkpoint_count=checkpoints,
        cached_pages=result.cached_pages,
        temporary_file_count=0,
        package_sha256=package_hash,
    )


def _run_successful_export(
    number: int,
    fixture: SoakFixture,
    exporter: Any,
    repository: JobRepository,
    props: ProjectVideoProps,
    fingerprint: str,
    *,
    label: str,
) -> tuple[VideoExportResult, tuple[str, ...], int]:
    record = _enqueue_and_claim(repository, fixture.project_id, fingerprint, f"{label}-{number}")
    context = PersistentRenderExecutionContext(
        job_id=record.id,
        project_dir=fixture.project_root,
        repository=repository,
        input_fingerprint=fingerprint,
    )
    result = exporter.export(fixture.project_id, context=context, props_override=props)
    repository.succeed(record.id, result.model_dump(mode="json"))
    return result, (str(record.id),), len(repository.list_checkpoints(record.id))


def _run_recovery_cycle(
    number: int,
    fixture: SoakFixture,
    exporter: Any,
    repository: JobRepository,
    props: ProjectVideoProps,
    fingerprint: str,
) -> tuple[VideoExportResult, tuple[str, ...], int]:
    record = _enqueue_and_claim(repository, fixture.project_id, fingerprint, f"recovery-{number}")
    first_context = PersistentRenderExecutionContext(
        job_id=record.id,
        project_dir=fixture.project_root,
        repository=repository,
        input_fingerprint=fingerprint,
    )
    try:
        exporter.export(
            fixture.project_id,
            context=_InterruptAfterPageCheckpoint(first_context, page_order=1),
            props_override=props,
        )
    except ControlledInterruption:
        pass
    else:
        raise RuntimeError("DP45 recovery injection did not interrupt an export")
    repository.recover_interrupted_jobs()
    paused = repository.get(record.id)
    if paused.status is not JobStatus.PAUSED:
        raise RuntimeError("DP45 interrupted export was not made resumable")
    if PersistentRenderExecutionContext(
        job_id=record.id,
        project_dir=fixture.project_root,
        repository=repository,
        input_fingerprint=fingerprint,
    ).restore() is None:
        raise RuntimeError("DP45 interrupted export has no verified checkpoint")
    repository.resume(record.id)
    resumed = repository.claim_next(JobType.EXPORT_PACKAGE)
    if resumed is None or resumed.id != record.id:
        raise RuntimeError("DP45 interrupted export could not be reclaimed")
    recovery_context = PersistentRenderExecutionContext(
        job_id=record.id,
        project_dir=fixture.project_root,
        repository=repository,
        input_fingerprint=fingerprint,
    )
    result = exporter.export(fixture.project_id, context=recovery_context, props_override=props)
    repository.succeed(record.id, result.model_dump(mode="json"))
    return result, (str(record.id),), len(repository.list_checkpoints(record.id))


def _run_cancel_retry_cycle(
    number: int,
    fixture: SoakFixture,
    exporter: Any,
    repository: JobRepository,
    props: ProjectVideoProps,
    fingerprint: str,
) -> tuple[VideoExportResult, tuple[str, ...], int]:
    record = _enqueue_and_claim(repository, fixture.project_id, fingerprint, f"cancel-{number}")
    context = PersistentRenderExecutionContext(
        job_id=record.id,
        project_dir=fixture.project_root,
        repository=repository,
        input_fingerprint=fingerprint,
    )
    from workbench.jobs.execution import RenderCancelled

    try:
        exporter.export(
            fixture.project_id,
            context=_CancelAfterPageCheckpoint(context, page_order=1),
            props_override=props,
        )
    except RenderCancelled:
        pass
    else:
        raise RuntimeError("DP45 cancellation injection did not cancel an export")
    repository.recover_interrupted_jobs(
        lambda job: CheckpointStore(fixture.project_root).cleanup_temporary_paths(job.id)
    )
    cancelled = repository.get(record.id)
    if cancelled.status is not JobStatus.CANCELLED:
        raise RuntimeError("DP45 cancelled export was not finalized as cancelled")
    staging = fixture.project_root / "08_输出" / ".render-jobs" / str(record.id)
    if staging.exists():
        raise RuntimeError("DP45 cancellation cleanup left a staging directory")
    result, retry_ids, checkpoint_count = _run_successful_export(
        number,
        fixture,
        exporter,
        repository,
        props,
        fingerprint,
        label="retry",
    )
    return result, (str(record.id), *retry_ids), checkpoint_count + len(
        repository.list_checkpoints(record.id)
    )


def _enqueue_and_claim(
    repository: JobRepository, project_id: UUID, fingerprint: str, label: str
) -> JobRecord:
    created = repository.enqueue_or_get(
        JobSpec(
            project_id=project_id,
            job_type=JobType.EXPORT_PACKAGE,
            cache_key=f"dp45:{label}:{uuid4().hex}",
            input_fingerprint=fingerprint,
        )
    ).record
    claimed = repository.claim_next(JobType.EXPORT_PACKAGE)
    if claimed is None or claimed.id != created.id:
        raise RuntimeError("DP45 export job could not be claimed")
    return claimed


def _create_fixture(projects: Any, *, page_count: int) -> SoakFixture:
    project = projects.create("q")
    project_root = (projects.workspace_root / project.project_dir).resolve()
    pages: list[PageRecord] = []
    extractions: list[PageExtraction] = []
    confirmations: list[Confirmation] = []
    words: list[TranscriptWord] = []
    source_rows: list[dict[str, object]] = []
    for page_order in range(1, page_count + 1):
        page_id = uuid4()
        revision_id = uuid4()
        image = project_root / "02_pages" / f"page-{page_order:04d}.png"
        audio = project_root / "05_audio" / f"page-{page_order:04d}.wav"
        _write_page_image(image, page_order)
        _write_wav(audio, _DEFAULT_PAGE_DURATION_MS, page_order)
        start_ms = (page_order - 1) * _DEFAULT_PAGE_DURATION_MS
        end_ms = page_order * _DEFAULT_PAGE_DURATION_MS
        pages.append(
            PageRecord(
                id=page_id,
                order=page_order,
                title=f"DP45 page {page_order}",
                narration=NarrationRecord(
                    id=uuid4(),
                    revision_id=revision_id,
                    confirmed_revision_id=revision_id,
                    text=f"Synthetic DP45 narration {page_order}.",
                    status=NodeStatus.COMPLETED,
                    author="performance-fixture",
                ),
                audio=AudioRecord(
                    id=uuid4(),
                    status=NodeStatus.COMPLETED,
                    # The file is generated locally, but the fixture models the
                    # already-confirmed per-page delivery route.  This keeps the
                    # existing subtitle gate in scope without contacting HeyGen.
                    source="heygen",
                    relative_path=audio.relative_to(project_root).as_posix(),
                    duration_ms=_DEFAULT_PAGE_DURATION_MS,
                    cache_key=sha256_file(audio),
                    narration_revision_id=revision_id,
                    voice_id="synthetic-local-fixture",
                ),
            )
        )
        extractions.append(
            PageExtraction(
                id=uuid4(),
                order=page_order,
                title=f"DP45 page {page_order}",
                preview_path=image,
                extraction_method="image",
                source_ref="DP45-repeated-local-v1",
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
        words.append(
            TranscriptWord(
                text=f"DP45 {page_order}",
                start_ms=start_ms + 10,
                end_ms=end_ms - 10,
                confidence=1.0,
            )
        )
        source_rows.append(
            {
                "page_order": page_order,
                "image_sha256": sha256_file(image),
                "audio_sha256": sha256_file(audio),
            }
        )
    projects.save(
        project.model_copy(
            update={
                "pages": pages,
                "page_extractions": extractions,
                "narration_confirmations": confirmations,
                "transcript": Transcript(
                    words=words,
                    detected_language="en",
                    model="synthetic-dp45-fixture",
                    device="cpu",
                    created_at=datetime.now(UTC),
                ),
            }
        )
    )
    canonical = json.dumps(source_rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return SoakFixture(
        project_id=project.id,
        project_root=project_root,
        page_count=page_count,
        duration_ms=page_count * _DEFAULT_PAGE_DURATION_MS,
        source_manifest_sha256=hashlib.sha256(canonical).hexdigest(),
    )


def _write_page_image(path: Path, page_order: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    color = (page_order * 47 % 256, page_order * 83 % 256, page_order * 113 % 256)
    Image.new("RGB", (640, 360), color).save(path, format="PNG")


def _write_wav(path: Path, duration_ms: int, page_order: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = 16_000 * duration_ms // 1_000
    sample = page_order.to_bytes(2, byteorder="little", signed=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(sample * frames)


def _cycle_mode(number: int, recovery_every: int, cancellation_every: int) -> str:
    if cancellation_every and number % cancellation_every == 0:
        return "cancel_retry"
    if recovery_every and number % recovery_every == 0:
        return "recovery"
    return "normal"


def _temporary_file_count(root: Path) -> int:
    return sum(
        1
        for path in root.rglob("*")
        if ".tmp" in path.name and (path.is_file() or path.is_dir())
    )


def _prune_completed_cycle_artifacts(fixture: SoakFixture, job_ids: list[str]) -> list[str]:
    """Remove only validated-success history belonging to this isolated soak fixture.

    This is acceptance-run storage control, not product retention behaviour. It
    runs only after package validation and never touches failed/cancelled
    evidence roots. The final stable output and the configured most-recent
    versioned packages remain available.
    """

    output_root = (fixture.project_root / "08_输出").resolve()
    log_root = (fixture.project_root / "09_日志" / "render-jobs").resolve()
    staging_root = (output_root / ".render-jobs").resolve()
    pruned: list[str] = []
    for job_id in job_ids:
        UUID(job_id)
        package = output_root / f"制作包-{job_id}"
        staging = staging_root / job_id
        job_log = log_root / job_id
        removed_any = False
        for root, target in (
            (output_root, package),
            (staging_root, staging),
            (log_root, job_log),
        ):
            resolved = target.resolve()
            if root not in resolved.parents:
                raise RuntimeError("DP45 retention target escapes the isolated fixture")
            if resolved.is_dir():
                shutil.rmtree(resolved)
                removed_any = True
            elif resolved.exists():
                raise RuntimeError("DP45 retention target must be a directory")
        if removed_any:
            pruned.append(job_id)
    return pruned


def _child_processes_of_current_harness() -> list[str]:
    observed = list(SystemProcessProvider().snapshot())
    by_parent: dict[int, list[ProcessObservation]] = {}
    for item in observed:
        if item.parent_pid is not None:
            by_parent.setdefault(item.parent_pid, []).append(item)
    descendants: list[ProcessObservation] = []
    pending = [os.getpid()]
    while pending:
        parent = pending.pop()
        for child in by_parent.get(parent, []):
            descendants.append(child)
            pending.append(child.pid)
    return sorted(
        f"{item.pid}:{Path(item.executable).name}"
        for item in descendants
        if Path(item.executable).name.lower() in {"ffmpeg.exe", "ffprobe.exe", "node.exe"}
    )


def _validate_job_hygiene(repository: JobRepository) -> None:
    active = [
        job
        for job in repository.list_all()
        if job.status
        in {
            JobStatus.QUEUED,
            JobStatus.RUNNING,
            JobStatus.PAUSE_REQUESTED,
            JobStatus.CANCEL_REQUESTED,
        }
    ]
    if active:
        raise RuntimeError(f"DP45 queue still has active jobs: {[str(job.id) for job in active]}")


def _validate_ledger(paths: tuple[Path, ...], maximum_bytes: int) -> None:
    if not paths:
        raise RuntimeError("DP45 event ledger is missing")
    for path in paths:
        if not path.is_file() or path.stat().st_size <= 0:
            raise RuntimeError(f"DP45 event ledger segment is missing: {path}")
        if path.stat().st_size > maximum_bytes:
            raise RuntimeError(f"DP45 event ledger segment exceeded rotation budget: {path}")


def _rss_curve(events: list[dict[str, object]]) -> dict[str, int | None]:
    samples: list[int] = []
    for event in events:
        if event.get("type") != "sample":
            continue
        processes = event.get("processes")
        if not isinstance(processes, list):
            continue
        for process in processes:
            if not isinstance(process, dict) or process.get("pid") != os.getpid():
                continue
            rss = process.get("rss_bytes")
            if isinstance(rss, int):
                samples.append(rss)
    if not samples:
        return {"first_bytes": None, "last_bytes": None, "peak_bytes": None, "growth_bytes": None}
    return {
        "first_bytes": samples[0],
        "last_bytes": samples[-1],
        "peak_bytes": max(samples),
        "growth_bytes": samples[-1] - samples[0],
    }


def _sampler_payload(summary_path: Path, summary: dict[str, object]) -> dict[str, object]:
    return {
        "summary_relative_path": summary_path.name,
        "summary_sha256": sha256_file(summary_path),
        "sample_count": summary.get("sample_count"),
        "roots_not_observed": summary.get("roots_not_observed"),
        "temporary_space_peaks": summary.get("temporary_space_peaks"),
        "component_peaks": summary.get("component_peaks"),
    }


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"DP45 JSON object expected: {path}")
    return value


def _load_sampler_events(path: Path) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if isinstance(value, dict):
            events.append(value)
    return events


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
    if not run_id.startswith("r-soak-"):
        raise ValueError("DP45 soak run ID is invalid")
    return Path(output_root) / f"c-{manifest_sha256[:12]}" / run_id


def _require_windows_path_budget(run_root: Path) -> None:
    projected = (
        run_root
        / "w"
        / "q_20260813_0101"
        / "08_输出"
        / ".render-jobs"
        / ("0" * 8 + "-" + "0" * 4 + "-" + "0" * 4 + "-" + "0" * 4 + "-" + "0" * 12)
        / "pages"
        / ".page-0001.tmp.mp4"
    )
    if os.name == "nt" and len(str(projected)) >= _WINDOWS_ACCEPTANCE_PATH_LIMIT:
        raise ValueError(
            "DP45 soak root is too deep for Windows FFmpeg publication; choose a shorter path"
        )


def _require_test_results_child(repo_root: Path, output_root: Path) -> None:
    allowed_root = (repo_root / "test-results").resolve()
    try:
        output_root.relative_to(allowed_root)
    except ValueError as error:
        raise ValueError("output_root must remain inside repository test-results") from error


def _validate_options(
    *,
    duration_seconds: float,
    minimum_cycles: int,
    cycle_interval_seconds: float,
    page_count: int,
    recovery_every: int,
    cancellation_every: int,
    retain_completed_jobs: int,
) -> None:
    if duration_seconds < 0:
        raise ValueError("duration_seconds must not be negative")
    if minimum_cycles < 1:
        raise ValueError("minimum_cycles must be positive")
    if cycle_interval_seconds < 0:
        raise ValueError("cycle_interval_seconds must not be negative")
    if not 1 <= page_count <= 50:
        raise ValueError("page_count must be between 1 and 50")
    if recovery_every < 0 or cancellation_every < 0:
        raise ValueError("recovery and cancellation cadence must not be negative")
    if retain_completed_jobs < 1:
        raise ValueError("retain_completed_jobs must be positive")


def _write_new_json(path: Path, payload: object) -> None:
    if path.exists():
        raise FileExistsError(f"evidence already exists: {path}")
    if not path.parent.is_dir():
        raise FileNotFoundError(f"evidence directory is missing: {path.parent}")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
