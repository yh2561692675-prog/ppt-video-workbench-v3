from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from workbench.api.projects import Envelope, envelope
from workbench.fidelity.jobs import FidelityJobService
from workbench.fidelity.models import FidelityJobRecord, FidelityJobRequest, SlideFidelityPage
from workbench.fidelity.scanner import FidelityScanError


def create_fidelity_router(service: FidelityJobService) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/fidelity")

    @router.post("/jobs", response_model=Envelope[FidelityJobRecord], status_code=201)
    def create_job(project_id: UUID, request: FidelityJobRequest) -> Envelope[FidelityJobRecord]:
        try:
            return envelope(service.submit(project_id, request))
        except FidelityScanError as error:
            raise HTTPException(
                status_code=422, detail={"code": error.code, "message": str(error)}
            ) from error

    @router.get("/jobs/{job_id}", response_model=Envelope[FidelityJobRecord])
    def get_job(project_id: UUID, job_id: UUID) -> Envelope[FidelityJobRecord]:
        try:
            return envelope(service.get(project_id, job_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="fidelity job not found") from error

    @router.get("/pages", response_model=Envelope[list[SlideFidelityPage]])
    def pages(project_id: UUID) -> Envelope[list[SlideFidelityPage]]:
        try:
            return envelope(service.pages(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="fidelity pages not found") from error

    return router
