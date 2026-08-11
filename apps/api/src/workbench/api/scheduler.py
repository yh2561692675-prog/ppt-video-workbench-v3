from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from workbench.api.projects import Envelope, envelope
from workbench.scheduler.models import (
    BatchCreateRequest,
    BatchDispatchRequest,
    BatchDispatchResult,
    BatchProduction,
    BatchRerunRequest,
)
from workbench.scheduler.service import BatchSchedulerService, SchedulerConflict, SchedulerError


def create_scheduler_router(service: BatchSchedulerService) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/batch-productions")

    @router.get("", response_model=Envelope[list[BatchProduction]])
    def list_batches(project_id: UUID) -> Envelope[list[BatchProduction]]:
        try:
            return envelope(service.list_batches(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error

    @router.post("", status_code=status.HTTP_201_CREATED, response_model=Envelope[BatchProduction])
    def create_batch(project_id: UUID, request: BatchCreateRequest) -> Envelope[BatchProduction]:
        try:
            return envelope(service.create(project_id, request))
        except (SchedulerError, KeyError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("/{batch_id}", response_model=Envelope[BatchProduction])
    def get_batch(project_id: UUID, batch_id: UUID) -> Envelope[BatchProduction]:
        try:
            batch = service.get(batch_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="batch not found") from error
        if batch.project_id != project_id:
            raise HTTPException(status_code=404, detail="batch not found")
        return envelope(batch)

    @router.post("/{batch_id}/dispatch", response_model=Envelope[BatchDispatchResult])
    def dispatch(
        project_id: UUID, batch_id: UUID, request: BatchDispatchRequest | None = None
    ) -> Envelope[BatchDispatchResult]:
        _ensure_project_batch(service, project_id, batch_id)
        request = request or BatchDispatchRequest()
        if service.get(batch_id).night_queue and not request.allow_night:
            raise HTTPException(status_code=409, detail="batch is reserved for the night queue")
        try:
            return envelope(service.dispatch(batch_id, request))
        except SchedulerError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/{batch_id}/sync", response_model=Envelope[BatchProduction])
    def sync(project_id: UUID, batch_id: UUID) -> Envelope[BatchProduction]:
        _ensure_project_batch(service, project_id, batch_id)
        return envelope(service.sync(batch_id))

    @router.post("/{batch_id}/rerun-failed", response_model=Envelope[BatchProduction])
    def rerun_failed(
        project_id: UUID, batch_id: UUID, request: BatchRerunRequest
    ) -> Envelope[BatchProduction]:
        _ensure_project_batch(service, project_id, batch_id)
        try:
            return envelope(service.rerun_failed(batch_id, request))
        except SchedulerConflict as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="batch item not found") from error

    return router


def _ensure_project_batch(service: BatchSchedulerService, project_id: UUID, batch_id: UUID) -> None:
    try:
        batch = service.get(batch_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="batch not found") from error
    if batch.project_id != project_id:
        raise HTTPException(status_code=404, detail="batch not found")
