from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from workbench.main import create_app


def test_project_lifecycle_persists_across_application_restart(tmp_path: Path) -> None:
    first_app = create_app(tmp_path)
    with TestClient(first_app) as client:
        created = client.post("/api/projects", json={"name": "计算机类专业介绍"})
        assert created.status_code == 201
        project = created.json()["data"]
        project_id = UUID(project["id"])
        assert project["project_dir"].startswith("计算机类专业介绍_")
        assert project["current_step"] == 1
        project_dir = tmp_path / project["project_dir"]
        assert (project_dir / "project.json").is_file()
        assert sorted(path.name for path in project_dir.iterdir() if path.is_dir()) == [
            "01_源文件",
            "02_页面预览",
            "03_文字识别",
            "04_旁白",
            "05_音频",
            "06_字幕",
            "07_视频工程",
            "08_输出",
            "09_日志",
        ]

        changed = client.patch(f"/api/projects/{project_id}/step", json={"step": 4})
        assert changed.status_code == 200
        assert changed.json()["data"]["current_step"] == 4

    second_app = create_app(tmp_path)
    with TestClient(second_app) as restarted_client:
        restored = restarted_client.get(f"/api/projects/{project_id}")
        assert restored.status_code == 200
        assert restored.json()["data"]["current_step"] == 4


def test_duplicate_names_get_distinct_project_directories(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path)) as client:
        first = client.post("/api/projects", json={"name": "新高一规划"}).json()["data"]
        second = client.post("/api/projects", json={"name": "新高一规划"}).json()["data"]

    assert first["project_dir"] != second["project_dir"]
    assert second["project_dir"].endswith("_2")


def test_pause_and_resume_are_persisted_and_return_envelopes(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path)) as client:
        project = client.post("/api/projects", json={"name": "图片课件视频"}).json()["data"]
        project_id = project["id"]

        paused = client.post(f"/api/projects/{project_id}/pause").json()
        resumed = client.post(f"/api/projects/{project_id}/resume").json()

    assert paused["data"]["id"] == project["id"]
    assert paused["data"]["status"] == "paused"
    assert paused["data"]["updated_at"] != project["updated_at"]
    assert paused["error"] is None
    assert paused["request_id"]
    assert resumed["data"]["status"] == "not_started"
    assert resumed["error"] is None
    assert resumed["request_id"]


def test_workspace_index_can_be_rebuilt_from_project_manifests(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    with TestClient(app) as client:
        expected = client.post("/api/projects", json={"name": "可重建索引"}).json()["data"]
    app.state.project_service.close()
    (tmp_path / "workspace.db").unlink()

    with TestClient(create_app(tmp_path)) as rebuilt_client:
        projects = rebuilt_client.get("/api/projects").json()["data"]

    assert [project["id"] for project in projects] == [expected["id"]]


def test_errors_use_the_structured_response_envelope(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path)) as client:
        invalid = client.post("/api/projects", json={"name": ""})
        missing = client.get(f"/api/projects/{UUID(int=0)}")

    assert invalid.status_code == 422
    assert invalid.json()["data"] is None
    assert invalid.json()["error"] == {
        "code": "validation_error",
        "message": "请求参数不符合接口契约",
        "action": "请检查标出的字段后重试",
        "blocking": True,
        "page_id": None,
        "job_id": None,
    }
    assert invalid.json()["request_id"]
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "project_not_found"
