from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from workbench.api.export_presets import create_export_presets_router
from workbench.exports.presets import ExportPresetService


def test_export_preset_routes_list_and_create_plan(tmp_path):
    project_id = uuid4()
    app = FastAPI()
    app.include_router(
        create_export_presets_router(
            ExportPresetService(tmp_path, project_dir_resolver=lambda _: "project")
        )
    )
    with TestClient(app) as client:
        presets = client.get(f"/api/projects/{project_id}/exports/presets")
        assert presets.status_code == 200
        assert len(presets.json()["data"]) >= 5
        plan = client.post(
            f"/api/projects/{project_id}/exports/plans",
            json={"preset_id": "master-4k-30", "output_name": "master"},
        )
        assert plan.status_code == 201
        assert plan.json()["data"]["preset"]["width"] == 3840
