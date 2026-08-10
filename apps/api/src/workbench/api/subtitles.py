from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from workbench.api.projects import Envelope, envelope
from workbench.subtitles.models import SubtitleBuildError, SubtitleTimeline
from workbench.subtitles.service import SubtitleGateBlocked, SubtitleService


def create_subtitle_router(service: SubtitleService) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/subtitles")

    @router.post(
        "/build", status_code=status.HTTP_201_CREATED, response_model=Envelope[SubtitleTimeline]
    )
    def build_subtitles(project_id: UUID) -> Envelope[SubtitleTimeline]:
        try:
            return envelope(service.build(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except SubtitleGateBlocked as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "audio_gate_blocked",
                    "message": str(error),
                    "action": "请处理所有音频门禁问题后再生成字幕",
                },
            ) from error
        except SubtitleBuildError as error:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "subtitle_build_rejected",
                    "message": str(error),
                    "action": "请补齐词级时间戳和页面音频时间轴后重试",
                },
            ) from error

    @router.get("", response_model=Envelope[SubtitleTimeline])
    def get_subtitles(project_id: UUID) -> Envelope[SubtitleTimeline]:
        try:
            return envelope(service.get(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="subtitle timeline not found") from error

    return router
