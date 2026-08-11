from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from workbench.api.assets import create_assets_router
from workbench.assets.service import AssetRegistryService
from workbench.domain.enums import JobType
from workbench.main import create_app


def test_asset_routes_import_list_and_license(tmp_path: Path) -> None:
    project_id = uuid4()
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "image.png").write_bytes(b"image")
    app = FastAPI()
    app.include_router(create_assets_router(AssetRegistryService(tmp_path, lambda _: "project")))

    with TestClient(app) as client:
        created = client.post(
            f"/api/projects/{project_id}/assets/import",
            json={"relative_path": "image.png", "kind": "image"},
        )
        assert created.status_code == 201
        asset_id = created.json()["data"]["asset_id"]
        listed = client.get(f"/api/projects/{project_id}/assets?kind=image")
        assert listed.status_code == 200
        assert listed.json()["data"][0]["asset_id"] == asset_id
        license_response = client.patch(
            f"/api/projects/{project_id}/assets/{asset_id}/license",
            json={"status": "confirmed", "owner": "test"},
        )
        assert license_response.status_code == 200
        assert license_response.json()["data"]["revision"] == 2


def test_derivative_job_route_materializes_asset_through_shared_worker_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WORKBENCH_ASYNC_RENDER_ENABLED", "false")
    app = create_app(tmp_path)
    project = app.state.project_service.create("asset derivative")
    project_root = tmp_path / project.project_dir
    Image.new("RGB", (80, 60), "blue").save(project_root / "source.png")

    with TestClient(app) as client:
        imported = client.post(
            f"/api/projects/{project.id}/assets/import",
            json={"relative_path": "source.png", "kind": "image"},
        )
        asset_id = imported.json()["data"]["asset_id"]
        submitted = client.post(
            f"/api/projects/{project.id}/assets/derivative-jobs",
            json={
                "parent_asset_id": asset_id,
                "operation": "thumbnail",
                "parameters": {"width": 40, "height": 40},
            },
        )
        job_id = submitted.json()["data"]["id"]
        claimed = app.state.project_service.jobs.claim_next(JobType.DERIVE_ASSET)
        assert claimed is not None
        app.state.asset_registry_service.handle_derivative_job(claimed)
        detail = client.get(f"/api/projects/{project.id}/jobs/{job_id}")

    assert submitted.status_code == 202
    assert detail.status_code == 200
    assert detail.json()["data"]["job"]["status"] == "succeeded"
    assert len(app.state.asset_registry_service.list_assets(project.id)) == 2
