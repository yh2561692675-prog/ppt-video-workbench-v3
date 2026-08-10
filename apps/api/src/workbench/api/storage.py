from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from workbench.api.projects import Envelope, envelope
from workbench.cache.cleanup import CleanupError, CleanupPlan, CleanupResult, CleanupService


class CleanupEstimateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selection: list[str] | None = None


class CleanupExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: UUID
    confirmation_token: str


def create_storage_router(service: CleanupService) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/storage")

    @router.post("/cleanup/estimate", response_model=Envelope[CleanupPlan])
    def estimate_cleanup(
        project_id: UUID, request: CleanupEstimateRequest | None = None
    ) -> Envelope[CleanupPlan]:
        try:
            return envelope(service.estimate(project_id, request.selection if request else None))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except CleanupError as error:
            raise HTTPException(
                status_code=409,
                detail={"code": error.code, "message": str(error), "action": error.action},
            ) from error

    @router.post("/cleanup/execute", response_model=Envelope[CleanupResult])
    def execute_cleanup(
        project_id: UUID, request: CleanupExecuteRequest
    ) -> Envelope[CleanupResult]:
        try:
            return envelope(
                service.execute(project_id, request.plan_id, request.confirmation_token)
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except CleanupError as error:
            raise HTTPException(
                status_code=409,
                detail={"code": error.code, "message": str(error), "action": error.action},
            ) from error

    return router
