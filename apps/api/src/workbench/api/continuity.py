from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from workbench.api.projects import Envelope, envelope
from workbench.continuity.models import ContinuityPlan, ContinuityPlanCommand
from workbench.continuity.service import ContinuityConflict, ContinuityError, ContinuityService


def create_continuity_router(service: ContinuityService) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/continuity")

    @router.get("", response_model=Envelope[ContinuityPlan])
    def get_plan(project_id: UUID) -> Envelope[ContinuityPlan]:
        try:
            return envelope(service.get(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error

    @router.post("", status_code=status.HTTP_201_CREATED, response_model=Envelope[ContinuityPlan])
    def create_plan(project_id: UUID) -> Envelope[ContinuityPlan]:
        try:
            return envelope(service.create(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error

    @router.get("/revisions", response_model=Envelope[list[ContinuityPlan]])
    def revisions(project_id: UUID) -> Envelope[list[ContinuityPlan]]:
        try:
            return envelope(service.revisions(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error

    @router.post("/commands", response_model=Envelope[ContinuityPlan])
    def command(project_id: UUID, request: ContinuityPlanCommand) -> Envelope[ContinuityPlan]:
        try:
            return envelope(service.apply(project_id, request))
        except ContinuityConflict as error:
            raise HTTPException(
                status_code=409,
                detail={"code": "continuity_revision_conflict", "message": str(error)},
            ) from error
        except (ContinuityError, KeyError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return router
