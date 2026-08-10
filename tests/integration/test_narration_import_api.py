from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from workbench.domain.enums import NodeStatus
from workbench.domain.models import PageRecord, stable_page_id
from workbench.main import create_app


def _project_with_pages(client: TestClient, app: object) -> tuple[str, list[str]]:
    project = client.post("/api/projects", json={"name": "旁白导入测试"}).json()["data"]
    project_id = UUID(project["id"])
    service = app.state.project_service  # type: ignore[attr-defined]
    manifest = service.get(project_id)
    pages = [
        PageRecord(
            id=stable_page_id(project_id, order),
            order=order,
            title=title,
            status=NodeStatus.COMPLETED,
        )
        for order, title in [(1, "专业概览"), (2, "培养路径")]
    ]
    service.save(manifest.model_copy(update={"pages": pages}))
    return project["id"], [str(page.id) for page in pages]


def test_preview_and_commit_imported_narration_by_page_number(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project_id, page_ids = _project_with_pages(client, app)
        preview = client.post(
            f"/api/projects/{project_id}/narrations/import/preview",
            files={
                "file": (
                    "机械类旁白.txt",
                    "第1页\n专业概览旁白。\n\n第2页\n培养路径旁白。".encode(),
                    "text/plain",
                )
            },
        )

        assert preview.status_code == 200
        payload = preview.json()["data"]
        assert payload["source_name"] == "机械类旁白.txt"
        assert [item["page_id"] for item in payload["assignments"]] == page_ids
        assert [item["method"] for item in payload["assignments"]] == [
            "page_number",
            "page_number",
        ]
        assert [item["text"] for item in payload["assignments"]] == [
            "专业概览旁白。",
            "培养路径旁白。",
        ]

        committed = client.post(
            f"/api/projects/{project_id}/narrations/import/commit",
            json={
                "source_name": payload["source_name"],
                "assignments": [
                    {
                        "page_id": item["page_id"],
                        "text": item["text"],
                        "expected_revision_id": None,
                        "method": item["method"],
                    }
                    for item in payload["assignments"]
                ],
            },
        )

    assert committed.status_code == 201
    revisions = committed.json()["data"]
    assert [item["page_id"] for item in revisions] == page_ids
    assert [item["text"] for item in revisions] == ["专业概览旁白。", "培养路径旁白。"]
    saved = app.state.project_service.get(UUID(project_id))
    assert all(page.narration is not None for page in saved.pages)
    assert all(page.narration.status is NodeStatus.NEEDS_CONFIRMATION for page in saved.pages)


def test_preview_rejects_unsupported_file_type(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    with TestClient(app) as client:
        project_id, _ = _project_with_pages(client, app)
        response = client.post(
            f"/api/projects/{project_id}/narrations/import/preview",
            files={"file": ("旁白.pdf", b"%PDF", "application/pdf")},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "narration_import_rejected"
