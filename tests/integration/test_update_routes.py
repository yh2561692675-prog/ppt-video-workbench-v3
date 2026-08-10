from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from workbench.main import create_app
from workbench.updates.service import UpdateService, hash_update_package


def test_update_routes_expose_stable_state_without_local_paths(tmp_path: Path) -> None:
    package = tmp_path / "updates" / "1.1.0"
    package.mkdir(parents=True)
    (package / "runtime-manifest.json").write_text('{"version":"1.1.0"}', encoding="utf-8")
    (package / "healthy.txt").write_text("ok", encoding="utf-8")
    releases = tmp_path / "releases"
    releases.mkdir()
    (releases / "current").mkdir()
    (releases / "stable-manifest.json").write_text(
        json.dumps(
            {
                "version": "1.1.0",
                "channel": "stable",
                "notes": "安全更新",
                "size": sum(path.stat().st_size for path in package.rglob("*") if path.is_file()),
                "sha256": hash_update_package(package),
                "package_relative_path": "updates/1.1.0",
            }
        ),
        encoding="utf-8",
    )
    update_service = UpdateService(
        tmp_path,
        current_version="1.0.0",
        health_check=lambda path: (path / "healthy.txt").exists(),
    )

    with TestClient(create_app(tmp_path, update_service=update_service)) as client:
        candidate = client.get("/api/updates/check")
        assert candidate.status_code == 200
        assert candidate.json()["data"]["version"] == "1.1.0"
        assert str(tmp_path) not in candidate.text

        staged = client.post("/api/updates/stage", json={"package_relative_path": "updates/1.1.0"})
        assert staged.status_code == 200
        assert staged.json()["data"]["staged_version"] == "1.1.0"

        applied = client.post("/api/updates/apply")
        assert applied.status_code == 200
        assert applied.json()["data"]["status"] == "applied"
