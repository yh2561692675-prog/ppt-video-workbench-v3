from __future__ import annotations

from fastapi import APIRouter, HTTPException

from workbench.api.projects import Envelope, envelope
from workbench.updates.secure import (
    SecureUpdateClient,
    SecureUpdateError,
    UpdateOperationState,
    UpdateTarget,
)


def create_secure_updates_router(client: SecureUpdateClient) -> APIRouter:
    router = APIRouter(prefix="/api/updates/secure")

    @router.get("", response_model=Envelope[UpdateOperationState])
    def state() -> Envelope[UpdateOperationState]:
        return envelope(client.state_store.read())

    @router.post("/check", response_model=Envelope[UpdateTarget | None])
    def check(metadata_url: str) -> Envelope[UpdateTarget | None]:
        try:
            return envelope(client.refresh(metadata_url))
        except SecureUpdateError as error:
            raise _error(error) from error

    @router.post("/download", response_model=Envelope[UpdateOperationState])
    def download(candidate: UpdateTarget) -> Envelope[UpdateOperationState]:
        try:
            client.download(candidate)
            return envelope(client.state_store.read())
        except SecureUpdateError as error:
            raise _error(error) from error

    return router


def _error(error: SecureUpdateError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": error.code, "message": str(error), "action": error.action},
    )
