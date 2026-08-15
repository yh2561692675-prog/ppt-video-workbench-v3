"""HTTP surface for the local ASR/TTS model center."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from workbench.ai_models.models import (
    LocalModelDescriptorV1,
    LocalModelRecordV1,
    ModelRuntimeProbeV1,
)
from workbench.ai_models.provisioner import LocalModelProvisioner, ModelProvisionError
from workbench.ai_models.registry import LocalModelRegistry, ModelRegistryError
from workbench.ai_models.runtime import ModelRuntimeManager

from .projects import Envelope, envelope


class ModelProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device: str = Field(default="cpu", pattern=r"^(cpu|cuda|directml|metal)$")


class ModelInstallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    descriptor: LocalModelDescriptorV1
    source_relative_path: str = Field(min_length=1, max_length=1024)


def create_ai_models_router(
    workspace_root: Path,
    registry: LocalModelRegistry,
    provisioner: LocalModelProvisioner,
    runtime: ModelRuntimeManager,
) -> APIRouter:
    router = APIRouter(prefix="/api/ai/models")
    root = workspace_root.resolve()

    @router.get("", response_model=Envelope[list[LocalModelRecordV1]])
    def list_models(
        kind: str | None = Query(default=None, pattern=r"^(asr|tts|voice_clone|embedding)$"),
    ) -> Envelope[list[LocalModelRecordV1]]:
        return envelope(registry.list(kind=kind))

    @router.get("/{model_id}", response_model=Envelope[LocalModelRecordV1])
    def get_model(model_id: str) -> Envelope[LocalModelRecordV1]:
        try:
            return envelope(registry.get(model_id))
        except ModelRegistryError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.post(
        "/install",
        status_code=status.HTTP_201_CREATED,
        response_model=Envelope[LocalModelRecordV1],
    )
    def install_model(request: ModelInstallRequest) -> Envelope[LocalModelRecordV1]:
        source = (
            root / Path(*request.source_relative_path.replace("\\", "/").split("/"))
        ).resolve()
        try:
            source.relative_to(root)
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail="source path must stay in workspace",
            ) from error
        if not source.is_dir():
            raise HTTPException(status_code=422, detail="source path must be a workspace directory")
        try:
            record = provisioner.install_from_directory(request.descriptor, source)
        except ModelProvisionError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return envelope(record)

    @router.post("/{model_id}/probe", response_model=Envelope[ModelRuntimeProbeV1])
    def probe_model(model_id: str, request: ModelProbeRequest) -> Envelope[ModelRuntimeProbeV1]:
        try:
            return envelope(runtime.probe(model_id, device=request.device))
        except ModelRegistryError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    @router.post("/{model_id}/activate", response_model=Envelope[LocalModelRecordV1])
    def activate_model(model_id: str, revision: str) -> Envelope[LocalModelRecordV1]:
        try:
            return envelope(registry.activate(model_id, revision))
        except ModelRegistryError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.delete("/{model_id}/{revision}", status_code=status.HTTP_204_NO_CONTENT)
    def remove_model(model_id: str, revision: str) -> None:
        try:
            record = registry.get(model_id, revision)
            registry.remove(model_id, revision)
        except ModelRegistryError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        model_root = provisioner.model_root(model_id, revision)
        if model_root.exists():
            import shutil

            shutil.rmtree(model_root)
        del record

    return router
