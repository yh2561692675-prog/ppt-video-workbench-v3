from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from workbench.main import create_app
from workbench.p2 import P2FeatureFlags


def test_existing_app_keeps_p2_routes_off_by_default(tmp_path: Path) -> None:
    app = create_app(tmp_path, p2_flags=P2FeatureFlags())
    with TestClient(app) as client:
        assert client.get("/api/providers").status_code == 404


def test_existing_app_can_opt_into_provider_diagnostics(tmp_path: Path) -> None:
    app = create_app(tmp_path, p2_flags=P2FeatureFlags(provider_platform_enabled=True))
    with TestClient(app) as client:
        response = client.get("/api/providers")
    assert response.status_code == 200
    assert response.json() == []
