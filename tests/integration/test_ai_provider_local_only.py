from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from workbench.main import create_app


def test_application_starts_without_provider_credentials_or_remote_calls(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path)) as client:
        project = client.post("/api/projects", json={"name": "本地独立链路"})
        assert project.status_code == 201
        assert client.get("/api/ai/models").status_code == 200
        assert client.get("/api/ai/voices").status_code == 200
        assert client.get("/api/ai/content-assist").status_code == 200
        assert client.app.state.provider_governance is not None
        assert client.app.state.provider_cost_ledger.list() == []
        assert not (tmp_path / "settings" / "heygen-profiles.json").exists()
