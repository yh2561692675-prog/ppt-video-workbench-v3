from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from workbench.api.continuity import create_continuity_router
from workbench.continuity.service import ContinuityService


def test_continuity_route_creates_and_updates_transition(tmp_path):
    project_id = uuid4()
    app = FastAPI()
    app.include_router(
        create_continuity_router(
            ContinuityService(tmp_path, project_dir_resolver=lambda _: "project")
        )
    )
    with TestClient(app) as client:
        created = client.post(f"/api/projects/{project_id}/continuity")
        assert created.status_code == 201
        revision = created.json()["data"]["revision"]
        updated = client.post(
            f"/api/projects/{project_id}/continuity/commands",
            json={
                "expected_revision": revision,
                "kind": "upsert_overlay",
                "payload": {
                    "source_ref": "brand/logo.png",
                    "kind": "logo",
                    "start_ms": 0,
                    "duration_ms": 100,
                    "x": 0.8,
                    "y": 0.05,
                    "width": 0.1,
                    "height": 0.1,
                },
            },
        )
        assert updated.status_code == 200
        assert len(updated.json()["data"]["overlays"]) == 1
