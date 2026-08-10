from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from workbench.main import create_app
from workbench_peripheral_adapter.client import (
    DisabledPeripheralClient,
    HttpPeripheralClient,
)


def test_workbench_starts_when_peripheral_is_disabled(tmp_path) -> None:
    app = create_app(tmp_path, peripheral_client=DisabledPeripheralClient())

    with TestClient(app) as client:
        health = client.get("/api/health")
        peripheral = client.get("/api/peripheral/status")

    assert health.status_code == 200
    assert peripheral.status_code == 200
    assert peripheral.json() == {"status": "disabled"}


def test_workbench_starts_and_reports_degraded_when_host_is_down(tmp_path) -> None:
    def down(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("host stopped")

    peripheral_client = HttpPeripheralClient(
        "http://127.0.0.1:8765",
        timeout_seconds=0.01,
        transport=httpx.MockTransport(down),
    )
    app = create_app(tmp_path, peripheral_client=peripheral_client)

    with TestClient(app) as client:
        health = client.get("/api/health")
        peripheral = client.get("/api/peripheral/status")

    assert health.status_code == 200
    assert peripheral.status_code == 200
    assert peripheral.json() == {"status": "degraded"}


def test_workbench_reports_available_when_host_health_is_ok(tmp_path) -> None:
    def healthy(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/v1/health"
        return httpx.Response(
            200,
            request=request,
            json={
                "status": "ok",
                "schema_version": "1.0",
                "component_version": "0.1.0",
            },
        )

    peripheral_client = HttpPeripheralClient(
        "http://127.0.0.1:8765",
        transport=httpx.MockTransport(healthy),
    )
    app = create_app(tmp_path, peripheral_client=peripheral_client)

    with TestClient(app) as client:
        response = client.get("/api/peripheral/status")

    assert response.status_code == 200
    assert response.json() == {"status": "available"}


def test_workbench_job_route_forwards_frozen_dto(tmp_path) -> None:
    job_id = uuid4()
    project_id = uuid4()

    def submit(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/internal/v1/jobs"
        return httpx.Response(
            202,
            request=request,
            json={"job_id": str(job_id), "status": "queued", "created": True},
        )

    peripheral_client = HttpPeripheralClient(
        "http://127.0.0.1:8765",
        transport=httpx.MockTransport(submit),
    )
    app = create_app(tmp_path, peripheral_client=peripheral_client)
    payload = {
        "schema_version": "1.0",
        "job_id": str(job_id),
        "project_id": str(project_id),
        "job_type": "system.echo",
        "requested_by": "workbench",
        "priority": 50,
        "idempotency_key": uuid4().hex,
        "inputs": [],
        "parameters": {"text": "route test"},
        "created_at": datetime.now(UTC).isoformat(),
    }

    with TestClient(app) as client:
        response = client.post("/api/peripheral/jobs", json=payload)

    assert response.status_code == 202
    assert response.json() == {
        "job_id": str(job_id),
        "status": "queued",
        "created": True,
    }


def test_workbench_job_route_maps_host_down_to_safe_503(tmp_path) -> None:
    def down(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(r"C:\Users\Alice\secret host detail")

    peripheral_client = HttpPeripheralClient(
        "http://127.0.0.1:8765",
        transport=httpx.MockTransport(down),
    )
    app = create_app(tmp_path, peripheral_client=peripheral_client)
    payload = {
        "schema_version": "1.0",
        "job_id": str(uuid4()),
        "project_id": str(uuid4()),
        "job_type": "system.echo",
        "requested_by": "workbench",
        "priority": 50,
        "idempotency_key": uuid4().hex,
        "inputs": [],
        "parameters": {"text": "route test"},
        "created_at": datetime.now(UTC).isoformat(),
    }

    with TestClient(app) as client:
        response = client.post("/api/peripheral/jobs", json=payload)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "peripheral_unavailable"
    assert "Alice" not in response.text
    assert "secret" not in response.text


def test_workbench_health_survives_peripheral_storage_503(tmp_path) -> None:
    def storage_unavailable(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            request=request,
            json={
                "error": {
                    "code": "STORAGE_UNAVAILABLE",
                    "message": "外围存储暂不可用，请稍后重试。",
                    "retryable": True,
                    "correlation_id": str(uuid4()),
                }
            },
        )

    peripheral_client = HttpPeripheralClient(
        "http://127.0.0.1:8765",
        transport=httpx.MockTransport(storage_unavailable),
    )
    app = create_app(tmp_path, peripheral_client=peripheral_client)

    with TestClient(app) as client:
        health = client.get("/api/health")
        status = client.get("/api/peripheral/status")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert status.json() == {"status": "degraded"}
