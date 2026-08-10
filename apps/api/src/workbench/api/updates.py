from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from workbench.api.projects import Envelope, envelope
from workbench.updates.service import UpdateCandidate, UpdateError, UpdateService, UpdateState


class UpdateStageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package_relative_path: str = Field(min_length=1, max_length=240)


def create_updates_router(service: UpdateService) -> APIRouter:
    router = APIRouter(prefix="/api/updates")

    @router.get("", response_model=Envelope[UpdateState])
    def update_state() -> Envelope[UpdateState]:
        return envelope(service.state())

    @router.get("/check", response_model=Envelope[UpdateCandidate | None])
    def check_update(channel: str = "stable") -> Envelope[UpdateCandidate | None]:
        try:
            return envelope(service.check_update(channel))
        except UpdateError as error:
            raise _update_http_error(error) from error

    @router.post("/stage", response_model=Envelope[UpdateState])
    def stage_update(request: UpdateStageRequest) -> Envelope[UpdateState]:
        try:
            return envelope(service.stage_update_relative(request.package_relative_path))
        except UpdateError as error:
            raise _update_http_error(error) from error

    @router.post("/apply", response_model=Envelope[UpdateState])
    def apply_update() -> Envelope[UpdateState]:
        try:
            return envelope(service.apply_update())
        except UpdateError as error:
            raise _update_http_error(error) from error

    @router.post("/rollback", response_model=Envelope[UpdateState])
    def rollback_update() -> Envelope[UpdateState]:
        try:
            return envelope(service.rollback_update())
        except UpdateError as error:
            raise _update_http_error(error) from error

    return router


def _update_http_error(error: UpdateError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": error.code, "message": str(error), "action": error.action},
    )
