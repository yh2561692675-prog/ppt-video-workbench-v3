from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from workbench.main import create_app


def test_cleanup_route_requires_second_confirmation_and_preserves_protected_paths(
    tmp_path: Path,
) -> None:
    app = create_app(tmp_path)
    project = app.state.project_service.create("清理路由")
    root = tmp_path / project.project_dir
    rebuildable = root / "07_视频工程" / "segments" / "page-1.mp4"
    rebuildable.parent.mkdir(parents=True, exist_ok=True)
    rebuildable.write_bytes(b"segment")
    protected = root / "08_输出" / "最终视频.mp4"
    protected.parent.mkdir(parents=True, exist_ok=True)
    protected.write_bytes(b"final")

    with TestClient(app) as client:
        estimate = client.post(f"/api/projects/{project.id}/storage/cleanup/estimate")
        plan = estimate.json()["data"]
        rejected = client.post(
            f"/api/projects/{project.id}/storage/cleanup/execute",
            json={"plan_id": plan["id"], "confirmation_token": "wrong"},
        )
        executed = client.post(
            f"/api/projects/{project.id}/storage/cleanup/execute",
            json={
                "plan_id": plan["id"],
                "confirmation_token": plan["confirmation_token"],
            },
        )

    assert estimate.status_code == 200
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "cleanup_confirmation_required"
    assert executed.status_code == 200
    assert executed.json()["data"]["deleted_paths"] == ["07_视频工程/segments/page-1.mp4"]
    assert not rebuildable.exists()
    assert protected.exists()
