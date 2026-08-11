from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from workbench.api.projects import Envelope, envelope
from workbench.subtitles.workbench_models import (
    SubtitleTranslationRequest,
    SubtitleTranslationResult,
    SubtitleWorkbenchCommand,
    SubtitleWorkbenchDocument,
)
from workbench.subtitles.workbench_service import (
    SubtitleWorkbenchConflict,
    SubtitleWorkbenchError,
    SubtitleWorkbenchService,
)


def create_subtitle_workbench_router(service: SubtitleWorkbenchService) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/subtitle-workbench")

    @router.get("", response_model=Envelope[SubtitleWorkbenchDocument])
    def get_document(project_id: UUID) -> Envelope[SubtitleWorkbenchDocument]:
        try:
            return envelope(service.get(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error

    @router.post(
        "", status_code=status.HTTP_201_CREATED, response_model=Envelope[SubtitleWorkbenchDocument]
    )
    def create_document(project_id: UUID) -> Envelope[SubtitleWorkbenchDocument]:
        try:
            return envelope(service.create(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error

    @router.get("/revisions", response_model=Envelope[list[SubtitleWorkbenchDocument]])
    def get_revisions(project_id: UUID) -> Envelope[list[SubtitleWorkbenchDocument]]:
        try:
            return envelope(service.revisions(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error

    @router.post("/commands", response_model=Envelope[SubtitleWorkbenchDocument])
    def apply_command(
        project_id: UUID, command: SubtitleWorkbenchCommand
    ) -> Envelope[SubtitleWorkbenchDocument]:
        try:
            return envelope(service.apply(project_id, command))
        except SubtitleWorkbenchConflict as error:
            raise HTTPException(
                status_code=409,
                detail={"code": "subtitle_revision_conflict", "message": str(error)},
            ) from error
        except (SubtitleWorkbenchError, KeyError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/translate", response_model=Envelope[SubtitleTranslationResult])
    def translate(
        project_id: UUID, request: SubtitleTranslationRequest
    ) -> Envelope[SubtitleTranslationResult]:
        try:
            return envelope(service.translate(project_id, request))
        except (SubtitleWorkbenchError, KeyError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return router
