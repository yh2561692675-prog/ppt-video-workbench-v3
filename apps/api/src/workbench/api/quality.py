from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from workbench.api.projects import Envelope, envelope
from workbench.quality.jobs import (
    QualityJobRecord,
    QualityJobRequest,
    QualityJobService,
    QualityPathError,
    QualityRetryLimitError,
)


class QualityIssueAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["confirm", "retry"]
    note: str = ""


def create_quality_router(service: QualityJobService) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/quality")

    @router.post("/jobs", response_model=Envelope[QualityJobRecord], status_code=201)
    def create_job(project_id: UUID, request: QualityJobRequest) -> Envelope[QualityJobRecord]:
        try:
            return envelope(service.submit(project_id, request))
        except QualityPathError as error:
            raise HTTPException(
                status_code=422,
                detail={"code": error.code, "message": str(error)},
            ) from error

    @router.get("/jobs/{job_id}", response_model=Envelope[QualityJobRecord])
    def get_job(project_id: UUID, job_id: UUID) -> Envelope[QualityJobRecord]:
        try:
            return envelope(service.get(project_id, job_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="quality job not found") from error

    @router.get("/latest", response_model=Envelope[QualityJobRecord])
    def latest(project_id: UUID) -> Envelope[QualityJobRecord]:
        try:
            return envelope(service.latest(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="quality report not found") from error

    @router.get("/evidence/{evidence_path:path}", response_model=None)
    def evidence(project_id: UUID, evidence_path: str) -> FileResponse:
        try:
            path = service.evidence_path(project_id, evidence_path)
        except (FileNotFoundError, QualityPathError) as error:
            raise HTTPException(status_code=404, detail="quality evidence not found") from error
        return FileResponse(path=Path(path), filename=Path(path).name)

    @router.post("/jobs/{job_id}/retry", response_model=Envelope[QualityJobRecord], status_code=201)
    def retry(project_id: UUID, job_id: UUID) -> Envelope[QualityJobRecord]:
        try:
            return envelope(service.retry(project_id, job_id))
        except QualityRetryLimitError as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "quality_retry_limit_reached",
                    "message": "该质量任务已完成一次安全重试",
                    "action": "请检查新任务报告或人工处理问题",
                },
            ) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="quality job not found") from error

    @router.post(
        "/jobs/{job_id}/issues/{issue_id}/actions",
        response_model=Envelope[QualityJobRecord],
        status_code=201,
    )
    def issue_action(
        project_id: UUID,
        job_id: UUID,
        issue_id: UUID,
        request: QualityIssueAction,
    ) -> Envelope[QualityJobRecord]:
        try:
            if request.action == "retry":
                return envelope(service.retry(project_id, job_id))
            return envelope(service.confirm_issue(project_id, job_id, issue_id))
        except QualityRetryLimitError as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "quality_retry_limit_reached",
                    "message": "该质量任务已完成一次安全重试",
                    "action": "请检查新任务报告或人工处理问题",
                },
            ) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="quality issue not found") from error

    return router
