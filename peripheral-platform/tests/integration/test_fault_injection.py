from __future__ import annotations

import hashlib
import sqlite3
import time
from datetime import UTC, datetime
from threading import Thread
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from peripheral_contracts import (
    ActionRequest,
    ActionType,
    ArtifactRef,
    JobEnvelope,
    JobStatus,
)
from peripheral_host.api import create_internal_app


def _client(scheduler_bundle) -> tuple[TestClient, object, object, object]:
    scheduler, service, repositories, clock = scheduler_bundle
    return (
        TestClient(create_internal_app(service=service, scheduler=scheduler)),
        scheduler,
        service,
        repositories,
    )


def _mode(job: JobEnvelope, fail_mode: str, *, delay_ms: int = 0) -> JobEnvelope:
    return job.model_copy(
        update={
            "parameters": {
                "text": "fault injection",
                "fail_mode": fail_mode,
                "delay_ms": delay_ms,
            }
        }
    )


def test_unknown_protocol_writes_nothing(scheduler_bundle, job: JobEnvelope) -> None:
    client, _, service, _ = _client(scheduler_bundle)
    payload = job.model_dump(mode="json")
    payload["schema_version"] = "2.0"

    response = client.post("/internal/v1/jobs", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_SCHEMA_VERSION"
    assert service.count_jobs() == 0  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("path", "sha256", "expected_code"),
    [
        ("projects/input.txt", "0" * 64, "ARTIFACT_HASH_MISMATCH"),
        ("../outside.txt", hashlib.sha256(b"source").hexdigest(), "WORKSPACE_PATH_REJECTED"),
    ],
)
def test_invalid_input_never_creates_attempt(
    scheduler_bundle,
    job: JobEnvelope,
    path: str,
    sha256: str,
    expected_code: str,
) -> None:
    client, _, service, repositories = _client(scheduler_bundle)
    source = service.workspace_root / "projects" / "input.txt"  # type: ignore[attr-defined]
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    invalid = job.model_copy(
        update={
            "inputs": (
                ArtifactRef(
                    artifact_id=uuid4(),
                    kind="source",
                    path=path,
                    size_bytes=6,
                    sha256=sha256,
                ),
            )
        }
    )

    response = client.post(
        "/internal/v1/jobs",
        json=invalid.model_dump(mode="json"),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == expected_code
    assert service.count_jobs() == 0  # type: ignore[attr-defined]
    with repositories.jobs.database.read_connection() as connection:  # type: ignore[attr-defined]
        assert connection.execute("SELECT COUNT(*) FROM job_attempts").fetchone()[0] == 0


def test_echo_permanent_and_invalid_result_fail_without_artifacts(
    scheduler_bundle,
    job: JobEnvelope,
) -> None:
    scheduler, service, _, _ = scheduler_bundle
    permanent = service.submit_job(_mode(job, "permanent"))
    second_job = job.model_copy(update={"job_id": uuid4(), "idempotency_key": uuid4().hex})
    invalid = service.submit_job(_mode(second_job, "invalid_result"))

    scheduler.run_once()
    scheduler.run_once()

    permanent_status = service.get_job_status(permanent.job_id)
    assert permanent_status.status is JobStatus.FAILED
    assert permanent_status.attempt_count == 1
    assert permanent_status.error is not None
    assert permanent_status.error.code == "ECHO_PERMANENT_FAILURE"
    assert service.get_job_status(invalid.job_id).status is JobStatus.FAILED
    assert service.list_artifacts(invalid.job_id) == ()


def test_retryable_failure_stops_after_three_attempts(
    scheduler_bundle,
    job: JobEnvelope,
) -> None:
    scheduler, service, _, clock = scheduler_bundle
    submitted = service.submit_job(_mode(job, "retryable"))

    scheduler.run_once()
    assert service.get_job_status(submitted.job_id).status is JobStatus.RETRY_WAIT
    clock.advance(5)
    scheduler.run_once()
    clock.advance(30)
    scheduler.run_once()

    status = service.get_job_status(submitted.job_id)
    assert status.status is JobStatus.FAILED
    assert status.attempt_count == 3


def test_running_cancel_reaches_cancelled_and_leaves_no_temporary_files(
    scheduler_bundle,
    job: JobEnvelope,
) -> None:
    scheduler, service, _, _ = scheduler_bundle
    submitted = service.submit_job(_mode(job, "none", delay_ms=5000))
    worker = Thread(target=scheduler.run_once, daemon=True)
    worker.start()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if service.get_job_status(submitted.job_id).status is JobStatus.RUNNING:
            break
        time.sleep(0.02)
    action = ActionRequest(
        schema_version="1.0",
        action=ActionType.CANCEL,
        requested_by="fault-test",
        requested_at=datetime.now(UTC),
    )

    assert service.request_action(submitted.job_id, action).status is JobStatus.CANCELLING
    worker.join(timeout=5)

    assert service.get_job_status(submitted.job_id).status is JobStatus.CANCELLED
    assert list(service.workspace_root.rglob("*.tmp")) == []


def test_restart_recovers_orphaned_running_job(
    scheduler_bundle,
    job: JobEnvelope,
) -> None:
    scheduler, service, _, clock = scheduler_bundle
    submitted = service.submit_job(job)
    assert service.claim_next(clock.now()) is not None

    assert scheduler.recover_on_startup() == 1

    recovered = service.get_job_status(submitted.job_id)
    assert recovered.status is JobStatus.RETRY_WAIT
    assert recovered.next_attempt_at == clock.now()


def test_shutdown_grace_expiry_controls_active_module_cancellation(
    scheduler_bundle,
    job: JobEnvelope,
) -> None:
    scheduler, service, _, _ = scheduler_bundle
    submitted = service.submit_job(_mode(job, "none", delay_ms=5000))
    scheduler.start()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if service.get_job_status(submitted.job_id).status is JobStatus.RUNNING:
            break
        time.sleep(0.02)

    scheduler.stop(grace_seconds=0.05)

    assert service.get_job_status(submitted.job_id).status is JobStatus.CANCELLED


def test_sqlite_failure_returns_safe_503(
    scheduler_bundle,
    job: JobEnvelope,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, service, _ = _client(scheduler_bundle)

    def locked(_envelope: JobEnvelope) -> None:
        raise sqlite3.OperationalError("database is locked at F:\\private\\peripheral.db")

    monkeypatch.setattr(service, "submit_job", locked)

    response = client.post(
        "/internal/v1/jobs",
        json=job.model_dump(mode="json"),
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STORAGE_UNAVAILABLE"
    assert "database" not in response.text.lower()
    assert "F:\\" not in response.text
