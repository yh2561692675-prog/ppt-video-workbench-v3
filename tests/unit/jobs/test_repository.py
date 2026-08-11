from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from workbench.domain.enums import JobStatus, JobType
from workbench.jobs.repository import JobRepository, JobSpec
from workbench.storage.workspace_db import WorkspaceDatabase


def repository_at(path: Path) -> JobRepository:
    database = WorkspaceDatabase(path)
    database.initialize()
    return JobRepository(database)


def export_spec(project_id, fingerprint: str = "fingerprint-a", **changes) -> JobSpec:
    return JobSpec(
        project_id=project_id,
        job_type=JobType.EXPORT_PACKAGE,
        cache_key=f"export:{fingerprint}:{uuid4().hex}",
        input_fingerprint=fingerprint,
        idempotency_key=f"video-export:{project_id}:{fingerprint}",
        payload={"fingerprint": fingerprint},
        **changes,
    )


def test_enqueue_or_get_deduplicates_same_active_input(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    project_id = uuid4()
    spec = export_spec(project_id)

    first = repository.enqueue_or_get(spec)
    second = repository.enqueue_or_get(spec)

    assert first.created is True
    assert second.created is False
    assert second.record.id == first.record.id
    assert second.record.status is JobStatus.QUEUED


def test_claim_next_is_single_winner_and_updates_revision(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    submitted = repository.enqueue_or_get(export_spec(uuid4()))

    first = repository.claim_next(JobType.EXPORT_PACKAGE)
    second = repository.claim_next(JobType.EXPORT_PACKAGE)

    assert first is not None
    assert first.id == submitted.record.id
    assert first.status is JobStatus.RUNNING
    assert first.stage == "validating_input"
    assert first.revision == 2
    assert second is None


def test_progress_is_monotonic_and_heartbeat_increments_revision(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    job_id = repository.enqueue_or_get(export_spec(uuid4())).record.id

    repository.claim_next(JobType.EXPORT_PACKAGE)
    progressed = repository.update_progress(job_id, 0.4, stage="rendering_pages", message="page 1")
    heartbeated = repository.heartbeat(job_id)

    assert progressed.progress == 0.4
    assert progressed.stage == "rendering_pages"
    assert heartbeated.revision == progressed.revision + 1
    with pytest.raises(ValueError, match="must not decrease"):
        repository.update_progress(job_id, 0.3, stage="rendering_pages", message="stale")


def test_pause_resume_cancel_state_matrix(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    queued_id = repository.enqueue_or_get(export_spec(uuid4())).record.id
    assert repository.request_pause(queued_id).status is JobStatus.PAUSED
    assert repository.resume(queued_id).status is JobStatus.QUEUED
    assert repository.request_cancel(queued_id).status is JobStatus.CANCELLED

    running_id = repository.enqueue_or_get(export_spec(uuid4(), fingerprint="running")).record.id
    repository.claim_next(JobType.EXPORT_PACKAGE)
    assert repository.request_pause(running_id).status is JobStatus.PAUSE_REQUESTED
    assert repository.request_cancel(running_id).status is JobStatus.CANCEL_REQUESTED


def test_pause_request_preserves_an_in_flight_terminal_result(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    job_id = repository.enqueue_or_get(export_spec(uuid4(), fingerprint="pause-race")).record.id

    repository.claim_next(JobType.EXPORT_PACKAGE)
    assert repository.request_pause(job_id).status is JobStatus.PAUSE_REQUESTED

    completed = repository.succeed(job_id, {"package_relative_path": "08_output/package"})

    assert completed.status is JobStatus.SUCCEEDED


def test_succeed_and_retry_preserve_result_and_parent_link(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    original = repository.enqueue_or_get(export_spec(uuid4())).record
    repository.claim_next(JobType.EXPORT_PACKAGE)
    completed = repository.succeed(original.id, {"package_relative_path": "08_output/package"})

    retry = repository.enqueue_or_get(
        export_spec(
            original.project_id,
            fingerprint="retry",
            parent_job_id=original.id,
        )
    ).record

    assert completed.status is JobStatus.SUCCEEDED
    assert completed.result == {"package_relative_path": "08_output/package"}
    assert retry.id != original.id
    assert retry.parent_job_id == original.id
