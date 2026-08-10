from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from peripheral_contracts import ActionRequest, ActionType, JobEnvelope
from peripheral_host.api import create_internal_app


@pytest.fixture
def client(scheduler_bundle) -> TestClient:
    scheduler, service, _, _ = scheduler_bundle
    return TestClient(create_internal_app(service=service, scheduler=scheduler))


def _json(model: object) -> dict[str, object]:
    return model.model_dump(mode="json")  # type: ignore[attr-defined, no-any-return]


def test_submit_and_read_job(client: TestClient, job: JobEnvelope) -> None:
    created = client.post("/internal/v1/jobs", json=_json(job))

    assert created.status_code == 202
    assert created.json() == {
        "job_id": str(job.job_id),
        "status": "queued",
        "created": True,
    }
    status = client.get(f"/internal/v1/jobs/{job.job_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "queued"
    assert status.json()["schema_version"] == "1.0"


def test_submit_is_idempotent(client: TestClient, job: JobEnvelope) -> None:
    first = client.post("/internal/v1/jobs", json=_json(job))
    duplicate = job.model_copy(update={"job_id": uuid4()})
    second = client.post("/internal/v1/jobs", json=_json(duplicate))

    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json() == {
        "job_id": str(job.job_id),
        "status": "queued",
        "created": False,
    }


def test_list_artifacts_and_cancel_action(client: TestClient, job: JobEnvelope) -> None:
    client.post("/internal/v1/jobs", json=_json(job))
    artifacts = client.get(f"/internal/v1/jobs/{job.job_id}/artifacts")
    action = ActionRequest(
        schema_version="1.0",
        action=ActionType.CANCEL,
        requested_by="workbench",
        requested_at=datetime.now(UTC),
    )
    cancelled = client.post(
        f"/internal/v1/jobs/{job.job_id}/actions",
        json=_json(action),
    )

    assert artifacts.status_code == 200
    assert artifacts.json() == []
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_health_does_not_expose_database_path(client: TestClient) -> None:
    response = client.get("/internal/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "schema_version": "1.0",
        "component_version": "0.1.0",
    }


def test_unknown_schema_major_has_stable_422_error(
    client: TestClient,
    job: JobEnvelope,
) -> None:
    payload = _json(job)
    payload["schema_version"] = "2.0"

    response = client.post("/internal/v1/jobs", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "UNSUPPORTED_SCHEMA_VERSION"
    assert response.json()["error"]["retryable"] is False
    UUID(response.json()["error"]["correlation_id"])


def test_missing_job_and_invalid_action_have_stable_errors(
    client: TestClient,
    job: JobEnvelope,
) -> None:
    missing = client.get(f"/internal/v1/jobs/{uuid4()}")
    client.post("/internal/v1/jobs", json=_json(job))
    retry = ActionRequest(
        schema_version="1.0",
        action=ActionType.RETRY,
        requested_by="workbench",
        requested_at=datetime.now(UTC),
    )
    conflict = client.post(
        f"/internal/v1/jobs/{job.job_id}/actions",
        json=_json(retry),
    )

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "JOB_NOT_FOUND"
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "INVALID_JOB_ACTION"


def test_internal_error_does_not_expose_stack_path_or_module_stderr(
    scheduler_bundle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduler, service, _, _ = scheduler_bundle
    leaked = r"C:\Users\Alice\work\secret.py module stderr: provider-token"

    def fail(_job_id: UUID) -> None:
        raise RuntimeError(leaked)

    monkeypatch.setattr(service, "get_job_status", fail)
    client = TestClient(
        create_internal_app(service=service, scheduler=scheduler),
        raise_server_exceptions=False,
    )

    response = client.get(f"/internal/v1/jobs/{uuid4()}")
    rendered = response.text

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "Alice" not in rendered
    assert "secret.py" not in rendered
    assert "provider-token" not in rendered
