"""HTTP surface for durable, opt-in remote provider batch state."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from workbench.providers.batch import ProviderBatchJobV1, ProviderBatchService
from workbench.providers.batch.repository import ProviderBatchRepositoryError

from .projects import Envelope, envelope


class BatchCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1, max_length=128)
    operation_kind: str = Field(pattern=r"^(tts|asr|avatar|renderer)$")
    project_id: UUID
    revision_id: UUID
    page_ids: list[UUID] = Field(min_length=1, max_length=10_000)


def create_provider_batches_router(service: ProviderBatchService) -> APIRouter:
    router = APIRouter(prefix="/api/providers/batches")

    @router.post(
        "", status_code=status.HTTP_201_CREATED, response_model=Envelope[ProviderBatchJobV1]
    )
    def create_batch(request: BatchCreateRequest) -> Envelope[ProviderBatchJobV1]:
        try:
            return envelope(
                service.create(
                    provider_id=request.provider_id,
                    operation_kind=request.operation_kind,
                    project_id=request.project_id,
                    revision_id=request.revision_id,
                    page_ids=request.page_ids,
                )
            )
        except ProviderBatchRepositoryError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.get("/{job_id}", response_model=Envelope[ProviderBatchJobV1])
    def get_batch(job_id: UUID) -> Envelope[ProviderBatchJobV1]:
        try:
            return envelope(service.repository.get(job_id))
        except ProviderBatchRepositoryError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.post("/{job_id}/resume", response_model=Envelope[list[UUID]])
    def resume_batch(job_id: UUID) -> Envelope[list[UUID]]:
        try:
            return envelope([item.item_id for item in service.resume(job_id)])
        except ProviderBatchRepositoryError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    return router
