from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from workbench.api.projects import Envelope, envelope
from workbench.exports.presets import (
    ExportPlan,
    ExportPlanRequest,
    ExportPreset,
    ExportPresetService,
)


def create_export_presets_router(service: ExportPresetService) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/exports")

    @router.get("/presets", response_model=Envelope[list[ExportPreset]])
    def presets(project_id: UUID) -> Envelope[list[ExportPreset]]:
        _ensure_project(service, project_id)
        return envelope(service.presets())

    @router.get("/plans", response_model=Envelope[list[ExportPlan]])
    def plans(project_id: UUID) -> Envelope[list[ExportPlan]]:
        try:
            return envelope(service.plans(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error

    @router.post("/plans", status_code=status.HTTP_201_CREATED, response_model=Envelope[ExportPlan])
    def create_plan(project_id: UUID, request: ExportPlanRequest) -> Envelope[ExportPlan]:
        try:
            return envelope(service.create_plan(project_id, request))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return router


def _ensure_project(service: ExportPresetService, project_id: UUID) -> None:
    try:
        service.project_dir_resolver(project_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="project not found") from error
