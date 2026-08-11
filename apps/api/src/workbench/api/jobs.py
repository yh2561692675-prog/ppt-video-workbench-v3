from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from workbench.api.projects import Envelope, envelope
from workbench.domain.models import JobRecord
from workbench.jobs.contracts import JobAttemptRecord, JobCheckpointRecord
from workbench.jobs.repository import JobTransitionConflict
from workbench.services.project_service import ProjectService


class JobActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["pause", "resume", "cancel", "confirm_retry"]
    expected_revision: int = Field(ge=1)


class JobDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job: JobRecord
    attempts: list[JobAttemptRecord]
    latest_checkpoint: JobCheckpointRecord | None = None


def create_jobs_router(service: ProjectService) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/jobs")

    @router.get("", response_model=Envelope[list[JobRecord]])
    def list_jobs(project_id: UUID) -> Envelope[list[JobRecord]]:
        _project_or_404(service, project_id)
        return envelope(service.jobs.list_for_project(project_id))

    @router.get("/{job_id}", response_model=Envelope[JobDetail])
    def get_job(project_id: UUID, job_id: UUID) -> Envelope[JobDetail]:
        job = _job_or_404(service, project_id, job_id)
        return envelope(
            JobDetail(
                job=job,
                attempts=service.jobs.list_attempts(job_id),
                latest_checkpoint=service.jobs.latest_checkpoint(job_id),
            )
        )

    @router.post("/{job_id}/actions", response_model=Envelope[JobRecord])
    def act_on_job(
        project_id: UUID, job_id: UUID, request: JobActionRequest
    ) -> Envelope[JobRecord]:
        _job_or_404(service, project_id, job_id)
        try:
            if request.action == "pause":
                updated = service.jobs.request_pause(
                    job_id, expected_revision=request.expected_revision
                )
            elif request.action == "resume":
                updated = service.jobs.resume(job_id, expected_revision=request.expected_revision)
            elif request.action == "confirm_retry":
                updated = service.jobs.confirm_paid_retry(
                    job_id, expected_revision=request.expected_revision
                )
            else:
                updated = service.jobs.request_cancel(
                    job_id, expected_revision=request.expected_revision
                )
        except JobTransitionConflict as error:
            raise HTTPException(
                status_code=409,
                detail={"code": "job_transition_conflict", "message": str(error)},
            ) from error
        return envelope(updated)

    return router


def _project_or_404(service: ProjectService, project_id: UUID) -> None:
    try:
        service.get(project_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="project not found") from error


def _job_or_404(service: ProjectService, project_id: UUID, job_id: UUID) -> JobRecord:
    try:
        job = service.jobs.get(job_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="job not found") from error
    if job.project_id != project_id:
        raise HTTPException(status_code=404, detail="job not found")
    return job
