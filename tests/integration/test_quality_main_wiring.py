from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from workbench.main import create_app


def test_main_app_wires_quality_service_and_routes(tmp_path: Path) -> None:
    app = create_app(tmp_path)

    assert app.state.quality_job_service.root == tmp_path.resolve()
    assert "/api/projects/{project_id}/quality/jobs" in app.openapi()["paths"]

    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/projects/{project_id}/quality/jobs" in response.json()["paths"]
