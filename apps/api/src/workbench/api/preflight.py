from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from workbench.api.projects import Envelope, envelope
from workbench.domain.issues import PreflightReport
from workbench.exports.preflight_report import report_markdown
from workbench.services.preflight_service import PreflightError, PreflightService
from workbench.video.package_service import (
    PackageError,
    VideoExportBlocked,
    VideoExportError,
    VideoExportResult,
    VideoExportService,
)
from workbench.video.render_service import RenderError


class PreflightRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: list[str] | None = None
    fresh: bool = True


class IssueConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: str = Field(min_length=1, max_length=120)
    note: str = Field(min_length=1, max_length=2_000)


def create_preflight_router(
    service: PreflightService,
    exporter: VideoExportService,
) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}")

    @router.post("/preflight", response_model=Envelope[PreflightReport])
    def run_preflight(
        project_id: UUID, request: PreflightRunRequest | None = None
    ) -> Envelope[PreflightReport]:
        try:
            report = service.run(
                project_id,
                request.scope if request else None,
                fresh=request.fresh if request else True,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        return envelope(report)

    @router.get("/preflight", response_model=Envelope[PreflightReport])
    def get_preflight(project_id: UUID) -> Envelope[PreflightReport]:
        try:
            return envelope(service.get(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error

    @router.post("/issues/{issue_id}/confirm", response_model=Envelope[PreflightReport])
    def confirm_issue(
        project_id: UUID,
        issue_id: UUID,
        request: IssueConfirmationRequest,
    ) -> Envelope[PreflightReport]:
        try:
            return envelope(
                service.confirm(
                    project_id,
                    issue_id,
                    actor=request.actor,
                    note=request.note,
                )
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except PreflightError as error:
            raise HTTPException(
                status_code=409,
                detail={"code": error.code, "message": str(error), "action": error.action},
            ) from error

    @router.get("/preflight/report", response_model=None)
    def export_preflight_report(
        project_id: UUID,
        format: str = Query(default="json", pattern="^(json|markdown)$"),
    ) -> Envelope[PreflightReport] | PlainTextResponse:
        try:
            report = service.get(project_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        if format == "markdown":
            project = service.projects.get(project_id)
            return PlainTextResponse(
                report_markdown(report, project.issue_confirmations),
                media_type="text/markdown; charset=utf-8",
            )
        return envelope(report)

    @router.post("/render", status_code=201, response_model=Envelope[VideoExportResult])
    def render(project_id: UUID) -> Envelope[VideoExportResult]:
        try:
            return envelope(exporter.export(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except VideoExportBlocked as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "preflight_blocked",
                    "message": str(error),
                    "action": "请完成当前预检中的阻断问题和待确认问题",
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
