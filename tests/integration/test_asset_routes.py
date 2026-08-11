from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from workbench.api.assets import create_assets_router
from workbench.assets.service import AssetRegistryService


def test_asset_routes_import_list_and_license(tmp_path) -> None:
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
