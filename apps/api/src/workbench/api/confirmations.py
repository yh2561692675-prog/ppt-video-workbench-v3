from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from workbench.api.projects import Envelope, envelope
from workbench.domain.confirmation import Confirmation, GateResult
from workbench.workflow.gates import ConfirmationError, NarrationGateService


class ConfirmationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_id: UUID
    actor: str = Field(min_length=1, max_length=80)
    conflict_resolution: str | None = None


class BatchConfirmationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: UUID
    revision_id: UUID
    conflict_resolution: str | None = None


class BatchConfirmationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor: str = Field(min_length=1, max_length=80)
    items: list[BatchConfirmationItem] = Field(min_length=1)


def create_confirmations_router(service: NarrationGateService) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}")

    @router.post("/confirmations/batch", response_model=Envelope[list[Confirmation]])
    def confirm_batch(
        project_id: UUID, request: BatchConfirmationCreate
    ) -> Envelope[list[Confirmation]]:
        try:
            confirmations = service.confirm_batch(
                project_id,
                [
                    (item.page_id, item.revision_id, item.conflict_resolution)
                    for item in request.items
                ],
                request.actor,
            )
        except ConfirmationError as error:
            raise _confirmation_http_error(error) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project or page not found") from error
        return envelope(confirmations)

    @router.post("/confirmations/{page_id}", response_model=Envelope[Confirmation])
    def confirm_page(
        project_id: UUID, page_id: UUID, request: ConfirmationCreate
    ) -> Envelope[Confirmation]:
        try:
            return envelope(
                service.confirm_narration(
                    page_id,
                    request.revision_id,
                    request.actor,
                    project_id,
                    conflict_resolution=request.conflict_resolution,
                )
            )
        except ConfirmationError as error:
            raise _confirmation_http_error(error) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project or page not found") from error

    @router.get("/workflow/audio-gate", response_model=Envelope[GateResult])
    def audio_gate(project_id: UUID) -> Envelope[GateResult]:
        try:
            return envelope(service.can_enter_audio(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error

    @router.post("/audio/enter", response_model=Envelope[GateResult])
    def enter_audio(project_id: UUID) -> Envelope[GateResult]:
        try:
            result = service.can_enter_audio(project_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        if not result.allowed:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "narration_gate_blocked",
                    "message": "旁白确认门禁尚未通过",
                    "action": "请根据逐页阻断原因完成确认",
                },
            )
        return envelope(result)

    return router


def _confirmation_http_error(error: ConfirmationError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": error.code, "message": str(error), "action": error.action},
    )
