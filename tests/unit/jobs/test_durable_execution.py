from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from workbench.domain.enums import AttemptStatus, JobType, LeaseStatus, WorkerStatus
from workbench.jobs.contracts import ResourceRequest, WorkerCapability
from workbench.jobs.leases import ResourceLeaseConflict, ResourceLeaseService
from workbench.jobs.repository import JobRepository, JobSpec, JobTransitionConflict
from workbench.storage.workspace_db import WorkspaceDatabase


def repository_at(path: Path) -> JobRepository:
    database = WorkspaceDatabase(path)
    database.initialize()
    return JobRepository(database)


def test_claim_creates_attempt_and_checkpoint_is_persistent(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    job = repository.enqueue_or_get(
        JobSpec(
            project_id=uuid4(),
            job_type=JobType.RENDER_PREVIEW,
            cache_key="preview:one",
            input_fingerprint="a" * 64,
            priority=10,
        )
    ).record

    claimed = repository.claim_next(
        JobType.RENDER_PREVIEW,
        worker_id="preview-worker",
        runtime_fingerprint="runtime-v1",
    )
    assert claimed is not None
    assert claimed.current_attempt_id is not None
    attempt = repository.current_attempt(job.id)
    assert attempt is not None
    assert attempt.status is AttemptStatus.RUNNING
    assert attempt.worker_id == "preview-worker"

    checkpoint = repository.record_checkpoint(job.id, {"stage": "mux", "progress": 0.5})
    assert checkpoint.sequence == 1
    restored = repository.latest_checkpoint(job.id)
    assert restored is not None
    assert restored.checkpoint["stage"] == "mux"
    assert repository.current_attempt(job.id).checkpoint_sequence == 1


def test_stale_attempt_cannot_heartbeat_and_terminal_state_updates_attempt(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    job = repository.enqueue_or_get(
        JobSpec(project_id=uuid4(), job_type=JobType.RENDER_EXPORT, cache_key="export:one")
    ).record
    claimed = repository.claim_next(JobType.RENDER_EXPORT)
    assert claimed is not None and claimed.current_attempt_id is not None
    attempt = repository.current_attempt(job.id)
    assert attempt is not None

    with pytest.raises(JobTransitionConflict, match="stale attempt"):
        repository.heartbeat(job.id, attempt_id=uuid4())

    repository.succeed(job.id, {"artifact": "ok"})
    assert repository.current_attempt(job.id).status is AttemptStatus.SUCCEEDED


def test_publication_is_idempotent_and_requires_matching_manifest(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    job = repository.enqueue_or_get(
        JobSpec(
            project_id=uuid4(),
            job_type=JobType.RENDER_EXPORT,
            cache_key="export:publication",
        )
    ).record
    claimed = repository.claim_next(JobType.RENDER_EXPORT)
    assert claimed is not None and claimed.current_attempt_id is not None
    attempt_id = claimed.current_attempt_id
    reserved = repository.reserve_publication(
        "publication:key", job.id, attempt_id, {"path": "output.mp4"}
    )
    same = repository.reserve_publication(
        "publication:key", job.id, attempt_id, {"path": "output.mp4"}
    )
    assert same == reserved
    published = repository.publish_publication(
        "publication:key",
        job_id=job.id,
        attempt_id=attempt_id,
        manifest_hash=reserved.manifest_hash,
    )
    assert published.state == "published"
    assert (
        repository.publish_publication(
            "publication:key",
            job_id=job.id,
            attempt_id=attempt_id,
            manifest_hash=reserved.manifest_hash,
        ).state
        == "published"
    )


def test_stale_attempt_cannot_publish_and_corrupted_output_is_reconciled(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    job = repository.enqueue_or_get(
        JobSpec(project_id=uuid4(), job_type=JobType.RENDER_EXPORT, cache_key="export:stale")
    ).record
    first = repository.claim_next(JobType.RENDER_EXPORT)
    assert first is not None and first.current_attempt_id is not None
    reserved = repository.reserve_publication(
        "publication:stale", job.id, first.current_attempt_id, {"path": "output.mp4"}
    )

    repository.request_pause(job.id)
    repository.mark_paused(job.id)
    repository.resume(job.id)
    second = repository.claim_next(JobType.RENDER_EXPORT)
    assert second is not None and second.current_attempt_id is not None

    with pytest.raises(JobTransitionConflict, match="stale attempt"):
        repository.publish_publication(
            "publication:stale",
            job_id=job.id,
            attempt_id=first.current_attempt_id,
            manifest_hash=reserved.manifest_hash,
        )

    current_reserved = repository.reserve_publication(
        "publication:current", job.id, second.current_attempt_id, {"path": "current.mp4"}
    )
    repository.publish_publication(
        "publication:current",
        job_id=job.id,
        attempt_id=second.current_attempt_id,
        manifest_hash=current_reserved.manifest_hash,
    )
    reconciled = repository.reconcile_publication("publication:current", lambda _: False)
    assert reconciled.state == "corrupted"


def test_action_rejects_stale_revision(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    job = repository.enqueue_or_get(
        JobSpec(project_id=uuid4(), job_type=JobType.RENDER_PREVIEW, cache_key="preview:revision")
    ).record

    with pytest.raises(JobTransitionConflict, match="revision mismatch"):
        repository.request_pause(job.id, expected_revision=job.revision + 1)

    paused = repository.request_pause(job.id, expected_revision=job.revision)
    assert paused.status.value == "paused"


def test_resource_lease_lifecycle_rejects_stale_generation(tmp_path: Path) -> None:
    database = WorkspaceDatabase(tmp_path / "workspace.db")
    database.initialize()
    service = ResourceLeaseService(database)
    worker = service.register_worker(
        "worker-1",
        runtime_fingerprint="runtime-v1",
        capabilities=WorkerCapability(job_types=[JobType.RENDER_PREVIEW.value]),
    )
    assert worker.status is WorkerStatus.ACTIVE
    job_id = uuid4()
    attempt_id = uuid4()
    lease = service.acquire(
        job_id=job_id,
        attempt_id=attempt_id,
        generation=1,
        worker_id=worker.id,
        request=ResourceRequest(cpu_cores=2, memory_mb=1024),
    )
    assert lease.status is LeaseStatus.ACTIVE
    renewed = service.heartbeat(lease.id, generation=1)
    assert renewed.revision == lease.revision + 1
    with pytest.raises(ResourceLeaseConflict, match="stale"):
        service.heartbeat(lease.id, generation=2)
    assert service.release(lease.id, generation=1).status is LeaseStatus.RELEASED
