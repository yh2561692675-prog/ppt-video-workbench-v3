from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from workbench.api.material_collections import create_material_collections_router
from workbench.materials.service import MaterialCollectionService


def test_material_collection_routes_create_command_and_sync(tmp_path) -> None:
    project_id = uuid4()
    app = FastAPI()
    app.include_router(create_material_collections_router(MaterialCollectionService(tmp_path)))
    section_id = str(uuid4())
    page_id = str(uuid4())
    payload = {
        "project_id": str(project_id),
        "documents": [],
        "presentations": [],
        "sections": [
            {"section_id": section_id, "order": 0, "title": "章节", "page_ids": [page_id]}
        ],
        "page_sequence": [
            {
                "material_page_id": page_id,
                "source_ref": "slides/1.png",
                "order": 0,
                "title": "页面",
                "section_id": section_id,
            }
        ],
        "outline_mode": "none",
        "merge_policy": "manual",
    }
    with TestClient(app) as client:
        created = client.post(f"/api/projects/{project_id}/material-collections", json=payload)
        assert created.status_code == 201
        disabled = client.post(
            f"/api/projects/{project_id}/material-collections/commands",
            json={
                "expected_revision": 1,
                "kind": "disable_page",
                "payload": {"material_page_id": page_id},
            },
        )
        assert disabled.status_code == 200
        preview = client.get(
            f"/api/projects/{project_id}/material-collections/sync-preview?timeline_revision=2"
        )
        assert preview.status_code == 200
        assert preview.json()["data"]["disabled_page_ids"] == [page_id]
