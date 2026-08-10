from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from workbench.api.projects import Envelope, envelope
from workbench.domain.effects import EffectPlanRecord
from workbench.effects.schema import EffectPlanV2
from workbench.effects.service import (
    EffectMutationResult,
    EffectService,
    EffectWorkspaceResponse,
)


class GenerateEffectsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_ids: list[UUID] | None = None
    force: bool = False


class UpdateEffectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int
    plan: EffectPlanV2
    locked: bool = False


class UnlockEffectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int


def create_effects_router(service: EffectService) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/effects")

    @router.get("/catalog")
    def catalog(project_id: UUID) -> Envelope[dict[str, object]]:
        _ensure_project(service, project_id)
        return envelope(service.catalog())

    @router.get("")
    def workspace(project_id: UUID) -> Envelope[EffectWorkspaceResponse]:
        try:
            return envelope(service.get_workspace(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error

    @router.post("/generate")
    def generate(
        project_id: UUID, request: GenerateEffectsRequest | None = None
    ) -> Envelope[EffectMutationResult]:
        try:
            request = request or GenerateEffectsRequest()
            return envelope(
                service.generate(project_id, page_ids=request.page_ids, force=request.force)
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error

    @router.put("/pages/{page_id}")
    def update_page(
        project_id: UUID, page_id: UUID, request: UpdateEffectRequest
    ) -> Envelope[EffectPlanRecord]:
        try:
            return envelope(
                service.update_page(
                    project_id,
                    page_id,
                    expected_revision=request.expected_revision,
                    plan=request.plan,
                    locked=request.locked,
                )
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="page not found") from error
        except ValueError as error:
            if str(error) == "effect_revision_conflict":
                raise HTTPException(status_code=409, detail={"code": str(error)}) from error
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/pages/{page_id}/unlock")
    def unlock_page(
        project_id: UUID, page_id: UUID, request: UnlockEffectRequest
    ) -> Envelope[EffectPlanRecord]:
        try:
            return envelope(
                service.unlock_page(
                    project_id, page_id, expected_revision=request.expected_revision
                )
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="page not found") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail={"code": str(error)}) from error

    return router


def _ensure_project(service: EffectService, project_id: UUID) -> None:
    try:
        service.projects.get(project_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="project not found") from error
