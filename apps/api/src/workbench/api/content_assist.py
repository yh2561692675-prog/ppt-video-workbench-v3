"""HTTP surface for candidate-only content assistance."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from workbench.content_assist.models import ContentAssistCandidateV1, ContentAssistRequestV1
from workbench.content_assist.repository import ContentAssistRepositoryError
from workbench.content_assist.service import ContentAssistService, ContentAssistUnavailable

from .projects import Envelope, envelope


def create_content_assist_router(service: ContentAssistService) -> APIRouter:
    router = APIRouter(prefix="/api/ai/content-assist")

    @router.get("", response_model=Envelope[list[ContentAssistCandidateV1]])
    def list_candidates() -> Envelope[list[ContentAssistCandidateV1]]:
        return envelope(service.repository.list())

    @router.post(
        "", status_code=status.HTTP_201_CREATED, response_model=Envelope[ContentAssistCandidateV1]
    )
    def create_candidate(
        request: ContentAssistRequestV1,
    ) -> Envelope[ContentAssistCandidateV1]:
        return envelope(service.create(request))

    @router.post("/{candidate_id}/accept", response_model=Envelope[ContentAssistCandidateV1])
    def accept_candidate(candidate_id: UUID) -> Envelope[ContentAssistCandidateV1]:
        try:
            return envelope(service.accept(candidate_id))
        except ContentAssistUnavailable as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except ContentAssistRepositoryError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    return router
