from __future__ import annotations

from collections.abc import Callable
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from workbench.api.projects import Envelope, envelope
from workbench.domain.enums import JobStatus
from workbench.jobs.repository import JobTransitionConflict
from workbench.video.models import VideoPreflight
from workbench.video.package_service import (
    PackageError,
    VideoExportBlocked,
    VideoExportError,
    VideoExportResult,
    VideoExportService,
)
from workbench.video.preview_service import VideoPreviewService
from workbench.video.render_job import RenderJobService
from workbench.video.render_service import RenderError


class PreflightRequest(BaseModel):
    reduced_motion: bool = False


class RenderJobActionRequest(BaseModel):
    action: Literal["pause", "resume", "cancel", "retry"]
    expected_revision: int | None = Field(default=None, ge=1)


class RenderJobSubmitRequest(BaseModel):
    preset_id: str | None = Field(default=None, min_length=1, max_length=64)


def create_video_router(
    service: VideoPreviewService,
    exporter: VideoExportService | None = None,
    render_jobs: RenderJobService | None = None,
    compatibility_preflight: Callable[[UUID], VideoPreflight | None] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/video")

    @router.post("/preflight", response_model=Envelope[VideoPreflight])
    def preflight(
        project_id: UUID, request: PreflightRequest | None = None
    ) -> Envelope[VideoPreflight]:
        try:
            if compatibility_preflight is not None:
                compatible = compatibility_preflight(project_id)
                if compatible is not None:
                    return envelope(compatible)
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

    @router.post("/render", status_code=201, response_model=None)
    def render_video(
        project_id: UUID, response: Response
    ) -> Envelope[dict[str, object]] | Envelope[VideoExportResult]:
        if (
            render_jobs is not None
            and render_jobs.worker is not None
            and render_jobs.worker.enabled
        ):
            try:
                submission = render_jobs.submit(project_id)
                response.status_code = 202 if submission.created else 200
                response.headers["Deprecation"] = "true"
                response.headers["Link"] = (
                    f'</api/projects/{project_id}/video/render-jobs>; rel="successor-version"'
                )
                if submission.created:
                    render_jobs.worker.wake()
                return envelope(
                    {"job": submission.job.model_dump(mode="json"), "created": submission.created}
                )
            except KeyError as error:
                raise HTTPException(status_code=404, detail="project not found") from error
            except VideoExportBlocked as error:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "video_preflight_blocked", "message": "视频预检尚未通过"},
                ) from error
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
                    "message": "视频预检尚未通过",
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

    @router.post("/render-jobs", status_code=202)
    def create_render_job(
        project_id: UUID,
        response: Response,
        request: RenderJobSubmitRequest | None = None,
    ) -> Envelope[dict[str, object]]:
        if render_jobs is None:
            raise HTTPException(status_code=503, detail="render worker unavailable")
        try:
            submission = (
                render_jobs.submit(project_id, preset_id=request.preset_id)
                if request is not None and request.preset_id is not None
                else render_jobs.submit(project_id)
            )
            response.status_code = 202 if submission.created else 200
            if submission.created and render_jobs.worker is not None:
                render_jobs.worker.wake()
            return envelope(
                {"job": submission.job.model_dump(mode="json"), "created": submission.created}
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except VideoExportBlocked as error:
            raise HTTPException(
                status_code=409, detail={"code": "video_preflight_blocked", "message": str(error)}
            ) from error

    @router.get("/render-jobs/current")
    def current_render_job(project_id: UUID) -> Envelope[dict[str, object] | None]:
        if render_jobs is None:
            raise HTTPException(status_code=503, detail="render worker unavailable")
        try:
            render_jobs.projects.get(project_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        jobs = [
            job
            for job in render_jobs.repository.list_all()
            if job.project_id == project_id and job.job_type.value == "export_package"
        ]
        active = next(
            (
                job
                for job in reversed(jobs)
                if job.status
                in {
                    JobStatus.QUEUED,
                    JobStatus.RUNNING,
                    JobStatus.PAUSE_REQUESTED,
                    JobStatus.PAUSED,
                    JobStatus.CANCEL_REQUESTED,
                }
            ),
            None,
        )
        current = active or (jobs[-1] if jobs else None)
        return envelope({"job": current.model_dump(mode="json")} if current else None)

    @router.get("/render-jobs/{job_id}", response_model=None)
    def get_render_job(
        project_id: UUID,
        job_id: UUID,
        response: Response,
        if_none_match: str | None = Header(default=None),
    ) -> Envelope[dict[str, object]] | Response:
        if render_jobs is None:
            raise HTTPException(status_code=503, detail="render worker unavailable")
        try:
            job = render_jobs.repository.get(job_id)
        except Exception as error:
            raise HTTPException(status_code=404, detail="job not found") from error
        if job.project_id != project_id:
            raise HTTPException(status_code=404, detail="job not found")
        etag = f'W/"job-{job.id}-{job.revision}"'
        response.headers["ETag"] = etag
        if if_none_match == etag:
            return Response(status_code=304, headers={"ETag": etag})
        return envelope({"job": job.model_dump(mode="json")})

    @router.post("/render-jobs/{job_id}/actions")
    def act_render_job(
        project_id: UUID, job_id: UUID, request: RenderJobActionRequest
    ) -> Envelope[dict[str, object]]:
        if render_jobs is None:
            raise HTTPException(status_code=503, detail="render worker unavailable")
        try:
            submission = render_jobs.act(
                project_id,
                job_id,
                request.action,
                expected_revision=request.expected_revision,
            )
            return envelope(
                {"job": submission.job.model_dump(mode="json"), "created": submission.created}
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="job not found") from error
        except (JobTransitionConflict, ValueError) as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "render_job_transition_conflict",
                    "message": "当前任务不允许执行该操作",
                    "action": "请刷新任务状态后重试",
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
