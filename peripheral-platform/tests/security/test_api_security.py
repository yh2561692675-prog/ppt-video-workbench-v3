from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from peripheral_host.api import create_internal_app
from peripheral_host.database import Database
from peripheral_host.module_runner import ModuleRegistry, ModuleRunner, echo_registered_module
from peripheral_host.repositories import Repositories
from peripheral_host.scheduler import Scheduler
from peripheral_host.service import JobService


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    workspace = tmp_path / "workspace"
    migrations = Path(__file__).resolve().parents[2] / "migrations"
    database = Database(workspace / "workspace-data" / "peripheral.db", migrations)
    database.initialize()
    registry = ModuleRegistry([echo_registered_module()])
    service = JobService(
        workspace_root=workspace,
        repositories=Repositories(database),
        registry=registry,
    )
    scheduler = Scheduler(
        service=service,
        runner=ModuleRunner(registry, workspace / "workspace-data" / "attempts"),
    )
    return TestClient(create_internal_app(service=service, scheduler=scheduler))


def test_mutating_routes_accept_only_json(client: TestClient) -> None:
    response = client.post(
        "/internal/v1/jobs",
        content="schema_version=1.0",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_request_body_is_limited_to_one_mebibyte(client: TestClient) -> None:
    oversized = json.dumps({"padding": "x" * (1024 * 1024)})

    response = client.post(
        "/internal/v1/jobs",
        content=oversized,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_BODY_TOO_LARGE"


def test_conflicting_content_length_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/internal/v1/jobs",
        content="{}",
        headers=[
            ("Content-Type", "application/json"),
            ("Content-Length", "2"),
            ("Content-Length", "3"),
        ],
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CONFLICTING_CONTENT_LENGTH"


def test_cors_does_not_allow_arbitrary_origin(client: TestClient) -> None:
    response = client.get(
        "/internal/v1/health",
        headers={"Origin": "https://attacker.example"},
    )
    preflight = client.options(
        "/internal/v1/jobs",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers
    assert "access-control-allow-origin" not in preflight.headers


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_documentation_is_disabled(client: TestClient, path: str) -> None:
    assert client.get(path).status_code == 404
