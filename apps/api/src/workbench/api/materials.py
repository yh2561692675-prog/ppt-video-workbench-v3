from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from workbench.api.projects import Envelope, envelope
from workbench.parsers.pdf_parser import OcrPolicy
from workbench.services.material_processing_service import (
    MaterialProcessingError,
    MaterialProcessingResult,
    MaterialProcessingService,
)


class MaterialParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ocr_policy: OcrPolicy = OcrPolicy.AUTO


def create_materials_router(service: MaterialProcessingService) -> APIRouter:
    router = APIRouter(prefix="/api/projects")

    @router.post(
        "/{project_id}/materials/parse",
        response_model=Envelope[MaterialProcessingResult],
    )
    def parse_materials(
        project_id: UUID, request: MaterialParseRequest
    ) -> Envelope[MaterialProcessingResult]:
        try:
            return envelope(service.process(project_id, request.ocr_policy))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except MaterialProcessingError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return router
