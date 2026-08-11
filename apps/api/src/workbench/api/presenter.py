from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from workbench.api.projects import Envelope, envelope
from workbench.domain.models import ProjectManifest
from workbench.domain.presenter import SlideAnchor
from workbench.media.presenter_probe import PresenterMediaError
from workbench.media.presenter_service import PresenterImportService
from workbench.services.presenter_analysis_service import (
    PresenterAnalysisError,
    PresenterAnalysisResult,
    PresenterAnalysisService,
    PresenterAnalysisUnavailable,
)
from workbench.timeline.presenter_builder import replace_anchor


class PresenterAnchorPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    sentence_ids: list[str] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    manual_lock: bool = True


def create_presenter_router(
    service: PresenterImportService,
    analysis: PresenterAnalysisService | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/projects")

    @router.post(
        "/{project_id}/presenter-source",
        status_code=status.HTTP_201_CREATED,
        response_model=Envelope[ProjectManifest],
    )
    async def import_presenter_source(
        project_id: UUID,
        file: Annotated[UploadFile, File()],
    ) -> Envelope[ProjectManifest]:
        try:
            return envelope(
                service.import_bytes(
                    project_id,
                    file.filename or "presenter.mp4",
                    await file.read(),
                )
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except PresenterMediaError as error:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": error.code,
                    "message": str(error),
                    "action": "请检查真人视频文件、音轨和格式后重新导入",
                },
            ) from error

    @router.patch(
        "/{project_id}/presenter-timeline/anchors/{page_id}",
        response_model=Envelope[ProjectManifest],
    )
    def patch_presenter_anchor(
        project_id: UUID,
        page_id: UUID,
        request: PresenterAnchorPatch,
    ) -> Envelope[ProjectManifest]:
        try:
            current = service.projects.get(project_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        timeline = current.presenter_timeline
        if timeline is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "presenter_timeline_missing", "current_revision": None},
            )
        if request.expected_revision != timeline.revision:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "presenter_timeline_revision_conflict",
                    "current_revision": timeline.revision,
                    "timeline_hash": timeline.timeline_hash,
                },
            )
        existing = next((item for item in timeline.anchors if item.page_id == page_id), None)
        if existing is None:
            raise HTTPException(status_code=404, detail="presenter anchor not found")
        source_revision = (
            timeline.source_version if request.manual_lock else existing.source_revision
        )
        try:
            replacement = SlideAnchor(
                page_id=page_id,
                start_ms=request.start_ms,
                end_ms=request.end_ms,
                sentence_ids=(
                    request.sentence_ids
                    if request.sentence_ids is not None
                    else existing.sentence_ids
                ),
                confidence=(
                    request.confidence if request.confidence is not None else existing.confidence
                ),
                status="confirmed" if request.manual_lock else existing.status,
                manual_lock=request.manual_lock,
                source_revision=source_revision,
            )
            updated_timeline = replace_anchor(
                timeline,
                replacement,
                expected_revision=request.expected_revision,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail={"code": "presenter_anchor_invalid", "message": str(error)},
            ) from error
        payload = current.model_dump(mode="python")
        payload["presenter_timeline"] = updated_timeline
        return envelope(service.projects.save(ProjectManifest.model_validate(payload)))

    @router.post(
        "/{project_id}/presenter-analysis",
        response_model=Envelope[PresenterAnalysisResult],
    )
    def analyze_presenter(project_id: UUID) -> Envelope[PresenterAnalysisResult]:
        if analysis is None:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "presenter_analysis_unavailable",
                    "message": "presenter analysis is unavailable",
                },
            )
        try:
            return envelope(analysis.analyze(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except PresenterAnalysisUnavailable as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "presenter_asr_unavailable", "message": str(error)},
            ) from error
        except PresenterAnalysisError as error:
            raise HTTPException(
                status_code=422,
                detail={"code": "presenter_analysis_rejected", "message": str(error)},
            ) from error

    return router
