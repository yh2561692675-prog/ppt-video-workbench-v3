from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict

from workbench.api.projects import Envelope, envelope
from workbench.domain.source_file import SourceFile
from workbench.services.import_service import ImportRejected, ImportService


class ImageOrderChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ordered_ids: list[UUID]


def create_sources_router(service: ImportService) -> APIRouter:
    router = APIRouter(prefix="/api/projects")

    @router.post("/{project_id}/sources", response_model=Envelope[list[SourceFile]])
    async def import_sources(
        project_id: UUID, files: Annotated[list[UploadFile], File()]
    ) -> Envelope[list[SourceFile]]:
        try:
            payloads = [(file.filename or "unnamed", await file.read()) for file in files]
            return envelope(service.import_batch(project_id, payloads))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except ImportRejected as error:
            raise HTTPException(
                status_code=422,
                detail={"code": "material_import_rejected", "message": str(error)},
            ) from error

    @router.patch("/{project_id}/sources/image-order", response_model=Envelope[list[SourceFile]])
    def reorder_images(project_id: UUID, request: ImageOrderChange) -> Envelope[list[SourceFile]]:
        try:
            return envelope(service.reorder_images(project_id, request.ordered_ids))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except ImportRejected as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return router
