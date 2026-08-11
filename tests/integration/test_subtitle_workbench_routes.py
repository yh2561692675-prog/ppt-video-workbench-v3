from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from workbench.api.subtitle_workbench import create_subtitle_workbench_router
from workbench.subtitles.workbench_service import SubtitleWorkbenchService


def test_subtitle_workbench_routes_edit_and_translate(tmp_path) -> None:
    project_id = uuid4()
    app = FastAPI()
    app.include_router(
        create_subtitle_workbench_router(
            SubtitleWorkbenchService(tmp_path, project_dir_resolver=lambda _: "project")
        )
    )
    with TestClient(app) as client:
        created = client.post(f"/api/projects/{project_id}/subtitle-workbench")
        assert created.status_code == 201
        document = created.json()["data"]
        cue_id = document["tracks"][0]["cues"]
        assert cue_id == []
        edited = client.post(
            f"/api/projects/{project_id}/subtitle-workbench/commands",
            json={
                "expected_revision": 1,
                "kind": "set_render_mode",
                "payload": {"render_mode": "burn_in"},
            },
        )
        assert edited.status_code == 200
        assert edited.json()["data"]["render_mode"] == "burn_in"
        translated = client.post(
            f"/api/projects/{project_id}/subtitle-workbench/translate",
            json={"language": "en", "label": "English"},
        )
        assert translated.status_code == 200
        assert {item["language"] for item in translated.json()["data"]["document"]["tracks"]} == {
            "zh-CN",
            "en",
        }
