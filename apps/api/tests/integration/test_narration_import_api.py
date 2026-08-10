from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from workbench.domain.models import PageRecord
from workbench.main import create_app


def _seed_pages(app, project_id: UUID) -> None:
    manifest = app.state.project_service.get(project_id)
    app.state.project_service.save(
        manifest.model_copy(
            update={
                "pages": [
                    PageRecord(id=UUID(int=1), order=1, title="专业概览"),
                    PageRecord(id=UUID(int=2), order=2, title="课程体系"),
                ]
            }
        )
    )


def test_narration_import_previews_numbered_sections_without_saving(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "旁白导入"}).json()["data"]
        _seed_pages(app, UUID(project["id"]))
        preview = client.post(
            f"/api/projects/{project['id']}/narrations/import/preview",
            files={
                "file": (
                    "旁白稿.txt",
                    (
                        "第1页 专业概览\\n这是第一页旁白。\\n"
                        "第2页 课程体系\\n这是第二页旁白。"
                    ).encode(),
                    "text/plain",
                )
            },
        )

    assert preview.status_code == 200
    assignments = preview.json()["data"]["assignments"]
    assert [item["method"] for item in assignments] == ["page_number", "page_number"]
    assert [item["text"] for item in assignments] == ["这是第一页旁白。", "这是第二页旁白。"]
    saved = app.state.project_service.get(project["id"])
    assert [page.narration for page in saved.pages] == [None, None]


def test_narration_import_falls_back_to_sequential_paragraphs_and_commits_drafts(
    tmp_path: Path,
) -> None:
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "连续稿导入"}).json()["data"]
        _seed_pages(app, UUID(project["id"]))
        preview = client.post(
            f"/api/projects/{project['id']}/narrations/import/preview",
            files={
                "file": (
                    "连续旁白.txt",
                    "第一页的完整介绍。\\n\\n第二页的完整介绍。".encode(),
                    "text/plain",
                )
            },
        ).json()["data"]
        assert [item["method"] for item in preview["assignments"]] == ["sequential", "sequential"]
        commit = client.post(
            f"/api/projects/{project['id']}/narrations/import/commit",
            json={
                "source_name": preview["source_name"],
                "assignments": [
                    {
                        "page_id": item["page_id"],
                        "text": item["text"],
                        "expected_revision_id": None,
                        "method": item["method"],
                    }
                    for item in preview["assignments"]
                ],
            },
        )

    assert commit.status_code == 201
    saved = app.state.project_service.get(project["id"])
    assert [page.narration.text for page in saved.pages if page.narration] == [
        "第一页的完整介绍。",
        "第二页的完整介绍。",
    ]
    assert all(
        page.narration.confirmed_revision_id is None for page in saved.pages if page.narration
    )
