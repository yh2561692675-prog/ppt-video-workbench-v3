from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from workbench.api.projects import Envelope, envelope
from workbench.assets.models import (
    AssetDeriveRequest,
    AssetImportRequest,
    AssetRecord,
    BrandPack,
    LicenseRecord,
)
from workbench.assets.service import AssetRegistryError, AssetRegistryService


def create_assets_router(service: AssetRegistryService) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/assets")

    @router.get("", response_model=Envelope[list[AssetRecord]])
    def list_assets(
        project_id: UUID, kind: str | None = Query(default=None, max_length=40)
    ) -> Envelope[list[AssetRecord]]:
        return envelope(service.list_assets(project_id, kind=kind))

    @router.get("/{asset_id}", response_model=Envelope[AssetRecord])
    def get_asset(project_id: UUID, asset_id: UUID) -> Envelope[AssetRecord]:
        try:
            return envelope(service.get(project_id, asset_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="asset not found") from error

    @router.post("/import", response_model=Envelope[AssetRecord], status_code=201)
    def import_asset(project_id: UUID, request: AssetImportRequest) -> Envelope[AssetRecord]:
        try:
            return envelope(service.import_asset(project_id, request))
        except AssetRegistryError as error:
            raise HTTPException(
                status_code=422, detail={"code": error.code, "message": str(error)}
            ) from error

    @router.post("/derive", response_model=Envelope[AssetRecord], status_code=201)
    def derive_asset(project_id: UUID, request: AssetDeriveRequest) -> Envelope[AssetRecord]:
        try:
            return envelope(service.derive(project_id, request))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="asset not found") from error
        except AssetRegistryError as error:
            raise HTTPException(
                status_code=422, detail={"code": error.code, "message": str(error)}
            ) from error

    @router.patch("/{asset_id}/license", response_model=Envelope[AssetRecord])
    def update_license(
        project_id: UUID, asset_id: UUID, license_record: LicenseRecord
    ) -> Envelope[AssetRecord]:
        try:
            return envelope(service.update_license(project_id, asset_id, license_record))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="asset not found") from error

    @router.get("/brand-packs/list", response_model=Envelope[list[BrandPack]])
    def brand_packs(project_id: UUID) -> Envelope[list[BrandPack]]:
        return envelope(service.brand_packs(project_id))

    @router.post("/brand-packs", response_model=Envelope[BrandPack], status_code=201)
    def create_brand_pack(project_id: UUID, pack: BrandPack) -> Envelope[BrandPack]:
        if pack.project_id not in {None, project_id}:
            raise HTTPException(status_code=422, detail="brand pack project does not match")
        try:
            return envelope(
                service.create_brand_pack(pack.model_copy(update={"project_id": project_id}))
            )
        except AssetRegistryError as error:
            raise HTTPException(
                status_code=422, detail={"code": error.code, "message": str(error)}
            ) from error

    return router
