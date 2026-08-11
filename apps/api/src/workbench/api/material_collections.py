from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from workbench.api.projects import Envelope, envelope
from workbench.materials.models import (
    MaterialCollection,
    MaterialCollectionCommand,
    MaterialSyncPreview,
)
from workbench.materials.service import MaterialCollectionError, MaterialCollectionService


def create_material_collections_router(service: MaterialCollectionService) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/material-collections")

    @router.get("", response_model=Envelope[MaterialCollection])
    def current(project_id: UUID) -> Envelope[MaterialCollection]:
        try:
            return envelope(service.current(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="material collection not found") from error

    @router.get("/revisions", response_model=Envelope[list[MaterialCollection]])
    def revisions(project_id: UUID) -> Envelope[list[MaterialCollection]]:
        return envelope(service.revisions(project_id))

    @router.post("", response_model=Envelope[MaterialCollection], status_code=201)
    def create(project_id: UUID, collection: MaterialCollection) -> Envelope[MaterialCollection]:
        if collection.project_id != project_id:
            raise HTTPException(status_code=422, detail="project id does not match collection")
        return envelope(service.create(collection))

    @router.post("/commands", response_model=Envelope[MaterialCollection])
    def command(
        project_id: UUID, request: MaterialCollectionCommand
    ) -> Envelope[MaterialCollection]:
        try:
            return envelope(service.apply(project_id, request))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="material collection not found") from error
        except MaterialCollectionError as error:
            raise HTTPException(
                status_code=409, detail={"code": error.code, "message": str(error)}
            ) from error

    @router.get("/sync-preview", response_model=Envelope[MaterialSyncPreview])
    def sync_preview(
        project_id: UUID, timeline_revision: int | None = None
    ) -> Envelope[MaterialSyncPreview]:
        try:
            return envelope(service.sync_preview(project_id, timeline_revision))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="material collection not found") from error

    return router
