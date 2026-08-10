from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from peripheral_contracts import EventEnvelope, JobEnvelope, JobStatus
from peripheral_host.artifacts import PublishedArtifact
from peripheral_host.repositories import Repositories


def test_duplicate_idempotency_key_returns_existing_job(
    repositories: Repositories,
    job: JobEnvelope,
):
    first = repositories.jobs.create(job)
    second = repositories.jobs.create(job.model_copy(update={"job_id": uuid4()}))

    assert second.job_id == first.job_id
    assert repositories.jobs.count() == 1


def test_job_round_trip_preserves_envelope(repositories: Repositories, job: JobEnvelope):
    created = repositories.jobs.create(job)

    loaded = repositories.jobs.get(job.job_id)

    assert loaded == created
    assert loaded is not None
    assert loaded.envelope == job
    assert loaded.status is JobStatus.QUEUED


def test_claim_next_uses_priority_then_creation_time(repositories: Repositories, job: JobEnvelope):
    now = datetime.now(UTC)
    low = job.model_copy(
        update={
            "job_id": uuid4(),
            "idempotency_key": uuid4().hex,
            "priority": 10,
            "created_at": now - timedelta(minutes=5),
        }
    )
    high = job.model_copy(
        update={
            "job_id": uuid4(),
            "idempotency_key": uuid4().hex,
            "priority": 90,
            "created_at": now,
        }
    )
    repositories.jobs.create(low)
    repositories.jobs.create(high)

    claimed = repositories.jobs.claim_next(now)

    assert claimed is not None
    assert claimed.job_id == high.job_id
    assert claimed.status is JobStatus.RUNNING


def test_event_repository_preserves_append_order(repositories: Repositories, job: JobEnvelope):
    repositories.jobs.create(job)
    first = EventEnvelope(
        schema_version="1.0",
        event_id=uuid4(),
        job_id=job.job_id,
        project_id=job.project_id,
        source="host",
        event_type="job.accepted",
        severity="info",
        occurred_at=datetime.now(UTC),
        data={"progress": 0},
    )
    second = first.model_copy(
        update={
            "event_id": uuid4(),
            "event_type": "job.started",
            "occurred_at": datetime.now(UTC),
        }
    )

    first_sequence = repositories.events.append(first)
    second_sequence = repositories.events.append(second)
    stored = repositories.events.list_for_job(job.job_id, after_sequence=first_sequence)

    assert second_sequence > first_sequence
    assert [event.envelope.event_type for event in stored] == ["job.started"]


def test_artifact_repository_versions_and_current_marker(
    repositories: Repositories,
    job: JobEnvelope,
    tmp_path: Path,
):
    repositories.jobs.create(job)
    first = PublishedArtifact(
        artifact_id=uuid4(),
        job_id=job.job_id,
        project_id=job.project_id,
        path=tmp_path / "v0001" / "echo.txt",
        relative_path="projects/demo/artifacts/echo-text/v0001/echo.txt",
        logical_name="echo-text",
        kind="text",
        version=1,
        size_bytes=3,
        sha256="a" * 64,
    )
    second = PublishedArtifact(
        artifact_id=uuid4(),
        job_id=job.job_id,
        project_id=job.project_id,
        path=tmp_path / "v0002" / "echo.txt",
        relative_path="projects/demo/artifacts/echo-text/v0002/echo.txt",
        logical_name="echo-text",
        kind="text",
        version=2,
        size_bytes=4,
        sha256="b" * 64,
    )

    assert repositories.artifacts.next_version(job.project_id, "echo-text") == 1
    repositories.artifacts.register_verified(first)
    repositories.artifacts.register_verified(second)
    records = repositories.artifacts.list_for_job(job.job_id)

    assert [record.version for record in records] == [1, 2]
    assert [record.is_current for record in records] == [False, True]
    assert repositories.artifacts.next_version(job.project_id, "echo-text") == 3
