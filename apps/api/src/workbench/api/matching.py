from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from workbench.api.projects import Envelope, envelope
from workbench.domain.matching import PageMatch
from workbench.services.matching_service import MatchingService, MatchRejected


class ManualMatchChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outline_ref: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=500)


def create_matching_router(service: MatchingService) -> APIRouter:
    router = APIRouter(prefix="/api/projects")

    @router.patch("/{project_id}/matches/{page_id}", response_model=Envelope[PageMatch])
    def change_match(
        project_id: UUID, page_id: UUID, request: ManualMatchChange
    ) -> Envelope[PageMatch]:
        try:
            return envelope(
                service.override(project_id, page_id, request.outline_ref, request.reason)
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="page match not found") from error
        except MatchRejected as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return router
