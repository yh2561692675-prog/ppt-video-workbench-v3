from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from peripheral_contracts import (
    ActionRequest,
    ActionType,
    ArtifactRef,
    JobEnvelope,
    JobResult,
    JobStatus,
    OutputArtifact,
)
from peripheral_host.database import Database
from peripheral_host.errors import ArtifactIntegrityError
from peripheral_host.module_runner import ModuleRegistry, echo_registered_module
from peripheral_host.repositories import Repositories
from peripheral_host.service import JobService


@pytest.fixture
def service_bundle(tmp_path: Path, migrations_dir: Path):
    workspace = tmp_path / "workspace"
    database = Database(workspace / "workspace-data" / "peripheral.db", migrations_dir)
    database.initialize()
    repositories = Repositories(database)
    service = JobService(
        workspace_root=workspace,
        repositories=repositories,
        registry=ModuleRegistry([echo_registered_module()]),
    )
    return service, repositories, workspace


def test_submit_is_idempotent(service_bundle, job: JobEnvelope):
    service, repositories, _ = service_bundle

    first = service.submit_job(job)
    second = service.submit_job(job.model_copy(update={"job_id": uuid4()}))

    assert second.job_id == first.job_id
    assert first.created is True
    assert second.created is False
    assert repositories.jobs.count() == 1
    assert [item.envelope.event_type for item in repositories.events.list_for_job(job.job_id)] == [
        "job.accepted"
    ]


def test_submit_verifies_all_inputs_before_insert(service_bundle, job: JobEnvelope):
    service, repositories, workspace = service_bundle
    source = workspace / "projects" / "source.txt"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    bad_input = ArtifactRef(
        artifact_id=uuid4(),
        kind="source",
        path="projects/source.txt",
        size_bytes=len(b"source"),
        sha256="0" * 64,
    )
    invalid = job.model_copy(update={"inputs": (bad_input,)})

    with pytest.raises(ArtifactIntegrityError):
        service.submit_job(invalid)

    assert repositories.jobs.count() == 0


def test_submit_rejects_invalid_echo_parameters_before_insert(service_bundle, job: JobEnvelope):
    service, repositories, _ = service_bundle
    invalid = job.model_copy(update={"parameters": {"delay_ms": 5}})

    with pytest.raises(ValueError):
        service.submit_job(invalid)

    assert repositories.jobs.count() == 0


def test_cancel_queued_job(service_bundle, job: JobEnvelope):
    service, _, _ = service_bundle
    service.submit_job(job)
    action = ActionRequest(
        schema_version="1.0",
        action=ActionType.CANCEL,
        requested_by="workbench",
        requested_at=datetime.now(UTC),
    )

    status = service.request_action(job.job_id, action)

    assert status.status is JobStatus.CANCELLED


def test_complete_attempt_registers_only_verified_artifact(
    service_bundle,
    job: JobEnvelope,
):
    service, repositories, workspace = service_bundle
    service.submit_job(job)
    service.state_machine.transition(job.job_id, JobStatus.QUEUED, JobStatus.RUNNING)
    attempt_root = (
        workspace
        / "projects"
        / str(job.project_id)
        / "state"
        / "jobs"
        / str(job.job_id)
        / "attempts"
        / "0001"
    )
    attempt = repositories.attempts.create(job.job_id, 1, attempt_root)
    attempt.root.mkdir(parents=True)
    payload = b"completed output"
    (attempt.root / "echo.txt").write_bytes(payload)
    result = JobResult(
        schema_version="1.0",
        job_id=job.job_id,
        outcome="succeeded",
        outputs=(
            OutputArtifact(
                logical_name="echo-text",
                kind="text",
                staged_path="echo.txt",
                size_bytes=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
            ),
        ),
    )

    status = service.complete_attempt(job.job_id, attempt.attempt_id, result)
    artifacts = service.list_artifacts(job.job_id)

    assert status.status is JobStatus.SUCCEEDED
    assert len(artifacts) == 1
    assert artifacts[0].verified_at is not None
    assert (workspace / artifacts[0].relative_path).read_bytes() == payload
