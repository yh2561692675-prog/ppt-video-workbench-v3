from pathlib import Path

from fastapi.testclient import TestClient
from workbench.domain.models import ProjectManifest
from workbench.main import create_app


def test_three_chinese_projects_survive_ten_restarts_and_index_rebuild(tmp_path: Path) -> None:
    names = ["计算机类专业介绍", "新高一规划", "图片课件视频"]
    with TestClient(create_app(tmp_path)) as client:
        created = [
            client.post("/api/projects", json={"name": name}).json()["data"] for name in names
        ]

    expected_ids = {project["id"] for project in created}
    for _ in range(10):
        with TestClient(create_app(tmp_path)) as restarted:
            restored = restarted.get("/api/projects").json()["data"]
            assert {project["id"] for project in restored} == expected_ids
            for project in restored:
                manifest_path = tmp_path / project["project_dir"] / "project.json"
                manifest = ProjectManifest.model_validate_json(manifest_path.read_text("utf-8"))
                assert str(manifest.id) == project["id"]

    (tmp_path / "workspace.db").unlink()
    with TestClient(create_app(tmp_path)) as rebuilt:
        restored_after_rebuild = rebuilt.get("/api/projects").json()["data"]

    assert {project["id"] for project in restored_after_rebuild} == expected_ids
