from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from workbench.api.projects import Envelope, envelope
from workbench.video.models import VideoPreflight
from workbench.video.package_service import (
    PackageError,
    VideoExportBlocked,
    VideoExportError,
    VideoExportResult,
    VideoExportService,
)
from workbench.video.preview_service import VideoPreviewService
from workbench.video.render_service import RenderError


class PreflightRequest(BaseModel):
    reduced_motion: bool = False


def create_video_router(
    service: VideoPreviewService, exporter: VideoExportService | None = None
) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/video")

    @router.post("/preflight", response_model=Envelope[VideoPreflight])
    def preflight(
        project_id: UUID, request: PreflightRequest | None = None
    ) -> Envelope[VideoPreflight]:
        try:
            return envelope(
                service.preflight(
                    project_id,
                    reduced_motion=request.reduced_motion if request is not None else None,
                )
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error

    @router.get("/preview", response_model=Envelope[VideoPreflight])
    def preview(project_id: UUID) -> Envelope[VideoPreflight]:
        try:
            return envelope(service.preview(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error

    @router.get("/assets/{asset_path:path}")
    def preview_asset(project_id: UUID, asset_path: str) -> FileResponse:
        try:
            return FileResponse(service.preview_asset(project_id, asset_path))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except FileNotFoundError as error:
            raise HTTPException(status_code=404, detail="preview asset not found") from error

    @router.post("/render", status_code=201, response_model=Envelope[VideoExportResult])
    def render_video(project_id: UUID) -> Envelope[VideoExportResult]:
        if exporter is None:
            raise HTTPException(status_code=503, detail="video exporter unavailable")
        try:
            return envelope(exporter.export(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except VideoExportBlocked as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "video_preflight_blocked",
                    "message": str(error),
                    "action": "请先完成第 6 步预览与完整预检",
                },
            ) from error
        except (VideoExportError, RenderError, PackageError) as error:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "video_export_rejected",
                    "message": "视频渲染或制作包校验失败",
                    "action": "请检查 FFmpeg、音频和页面预览后重试",
                },
            ) from error

    return router
