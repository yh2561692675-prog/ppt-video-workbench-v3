from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field
from workbench_peripheral_adapter import (
    ActionRequestDto,
    PeripheralClientProtocol,
    PeripheralUnavailable,
    SubmitJobDto,
)
from workbench_peripheral_adapter.dto import ArtifactInputDto

from workbench.business_modules.registry import validate_module_job_type
from workbench.peripheral_s1.coordinator import JobSpec, S1Coordinator


class S1JobRequest(BaseModel):
    module_id: str = Field(pattern=r"^P(?:0[3-9]|1[0-2])$")
    parameters: dict[str, Any] = Field(default_factory=dict)
    requested_by: str = Field(min_length=1, max_length=64)
    idempotency_key: str | None = None
    priority: int = Field(default=50, ge=0, le=100)
    project_revision: int = Field(default=1, ge=1)
    affected_page_ids: tuple[UUID, ...] = ()
    inputs: tuple[ArtifactInputDto, ...] = ()


def create_peripheral_s1_router(
    client: PeripheralClientProtocol,
    coordinator: S1Coordinator | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/s1")

    @router.post("/jobs/{job_type}")
    def submit(
        project_id: UUID, job_type: str, request: S1JobRequest, response: Response
    ) -> dict[str, object]:
        if not client.enabled:
            raise HTTPException(
                status_code=503,
                detail={"code": "peripheral_disabled", "message": "S1 外围能力未启用"},
            )
        try:
            module_id = validate_module_job_type(request.module_id, job_type)
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail={"code": "s1_job_type_mismatch", "message": str(error)},
            ) from error
        if coordinator is not None:
            try:
                submitted = coordinator.submit(
                    JobSpec(
                        project_id=project_id,
                        project_revision=request.project_revision,
                        module_id=module_id,
                        job_type=job_type,
                        affected_page_ids=request.affected_page_ids,
                        inputs=request.inputs,
                        parameters=request.parameters,
                        runtime_version="1.0.0",
                        requested_by=request.requested_by,
                        priority=request.priority,
                    )
                )
            except KeyError as error:
                raise HTTPException(
                    status_code=404,
                    detail={"code": "project_not_found", "message": "项目不存在"},
                ) from error
            response.status_code = (
                status.HTTP_202_ACCEPTED if submitted.created else status.HTTP_200_OK
            )
            return {
                "job_id": str(submitted.job_id),
                "status": submitted.status,
                "created": submitted.created,
                "execution": "peripheral",
            }
        job_id = uuid4()
        submit_request = SubmitJobDto(
            job_id=job_id,
            project_id=project_id,
            job_type=job_type,
            requested_by=request.requested_by,
            priority=request.priority,
            idempotency_key=request.idempotency_key or uuid4().hex,
            parameters={**request.parameters, "module_id": request.module_id},
            created_at=datetime.now(UTC),
        )
        try:
            result = client.submit_job(submit_request)
        except PeripheralUnavailable as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "peripheral_unavailable", "message": error.user_message},
            ) from error
        response.status_code = status.HTTP_202_ACCEPTED if result.created else status.HTTP_200_OK
        return {**result.model_dump(mode="json"), "execution": "peripheral"}

    @router.get("/jobs/{job_id}")
    def get_status(project_id: UUID, job_id: UUID) -> dict[str, object]:
        try:
            current = client.get_job_status(job_id)
            if current.project_id != project_id:
                raise HTTPException(status_code=404, detail={"code": "s1_job_not_found"})
            payload = current.model_dump(mode="json")
            if coordinator is not None and current.status == "succeeded":
                projection = coordinator.reconcile(job_id)
                payload["projection"] = {
                    "status": projection.status,
                    "reason": projection.reason,
                }
            return payload
        except PeripheralUnavailable as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "peripheral_unavailable", "message": error.user_message},
            ) from error

    @router.post("/jobs/{job_id}/actions")
    def action(project_id: UUID, job_id: UUID, request: ActionRequestDto) -> dict[str, object]:
        current = client.get_job_status(job_id)
        if current.project_id != project_id:
            raise HTTPException(status_code=404, detail={"code": "s1_job_not_found"})
        return client.request_action(job_id, request).model_dump(mode="json")

    return router
