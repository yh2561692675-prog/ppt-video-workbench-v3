from __future__ import annotations

from collections.abc import Callable
from typing import cast
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel
from workbench_peripheral_adapter import (
    ActionRequestDto,
    PeripheralClientProtocol,
    PeripheralRequestRejected,
    PeripheralUnavailable,
    SubmitJobDto,
)


def create_peripheral_router(client: PeripheralClientProtocol) -> APIRouter:
    router = APIRouter(prefix="/api/peripheral")

    @router.get("/status")
    def peripheral_status() -> dict[str, str]:
        if not client.enabled:
            return {"status": "disabled"}
        return {"status": "available" if client.probe() else "degraded"}

    @router.post("/jobs")
    def submit_job(request: SubmitJobDto, response: Response) -> dict[str, object]:
        result = _call(client.submit_job, request)
        response.status_code = status.HTTP_202_ACCEPTED if result.created else status.HTTP_200_OK
        return _dump(result)

    @router.get("/jobs/{job_id}")
    def get_job(job_id: UUID) -> dict[str, object]:
        return _dump(_call(client.get_job_status, job_id))

    @router.get("/jobs/{job_id}/artifacts")
    def list_artifacts(job_id: UUID) -> list[dict[str, object]]:
        return [_dump(item) for item in _call(client.list_artifacts, job_id)]

    @router.post("/jobs/{job_id}/actions")
    def request_action(job_id: UUID, request: ActionRequestDto) -> dict[str, object]:
        return _dump(_call(client.request_action, job_id, request))

    return router


def _call[**P, T](function: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    try:
        return function(*args, **kwargs)
    except PeripheralUnavailable as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "peripheral_unavailable",
                "message": error.user_message,
                "action": "可继续使用原有视频流程，稍后再试外围功能",
            },
        ) from error
    except PeripheralRequestRejected as error:
        raise HTTPException(
            status_code=error.status_code,
            detail={
                "code": error.code,
                "message": error.user_message,
                "action": "请检查外围任务输入或状态后重试",
            },
        ) from error


def _dump(model: BaseModel) -> dict[str, object]:
    return cast(dict[str, object], model.model_dump(mode="json"))
