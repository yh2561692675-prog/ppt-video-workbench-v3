from collections.abc import Callable
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from workbench.domain.confirmation import GateResult
from workbench.domain.models import ProblemDetails, ProjectManifest
from workbench.services.project_service import ProjectService


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)


class StepChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    step: int = Field(ge=1, le=7)


class Envelope[T](BaseModel):
    model_config = ConfigDict(extra="forbid")
    data: T
    error: ProblemDetails | None = None
    request_id: UUID


class DiskStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total: int
    used: int
    free: int


def envelope[T](data: T) -> Envelope[T]:
    return Envelope(data=data, request_id=uuid4())


def create_projects_router(
    service: ProjectService,
    audio_gate: Callable[[ProjectManifest], GateResult] | None = None,
    video_gate: Callable[[ProjectManifest], bool] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post(
        "/projects",
        status_code=status.HTTP_201_CREATED,
        response_model=Envelope[ProjectManifest],
    )
    def create_project(request: ProjectCreate) -> Envelope[ProjectManifest]:
        try:
            project = service.create(request.name)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return envelope(project)

    @router.get("/projects", response_model=Envelope[list[ProjectManifest]])
    def list_projects() -> Envelope[list[ProjectManifest]]:
        return envelope(service.list())

    @router.get("/projects/{project_id}", response_model=Envelope[ProjectManifest])
    def get_project(project_id: UUID) -> Envelope[ProjectManifest]:
        return envelope(_get_or_404(service, project_id))

    @router.patch("/projects/{project_id}/step", response_model=Envelope[ProjectManifest])
    def change_step(project_id: UUID, request: StepChange) -> Envelope[ProjectManifest]:
        try:
            if request.step >= 6 and audio_gate is not None:
                gate = audio_gate(service.get(project_id))
                if not gate.allowed:
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "code": "audio_gate_blocked",
                            "message": "音频路线尚未通过字幕门禁",
                            "action": "请处理所有音频门禁问题后再进入字幕步骤",
                        },
                    )
            if (
                request.step >= 7
                and video_gate is not None
                and not video_gate(service.get(project_id))
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "video_preflight_blocked",
                        "message": "视频完整预检尚未通过",
                        "action": "请先完成第 6 步预览与完整预检",
                    },
                )
            project = service.set_step(project_id, request.step)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        return envelope(project)

    @router.post("/projects/{project_id}/pause", response_model=Envelope[ProjectManifest])
    def pause_project(project_id: UUID) -> Envelope[ProjectManifest]:
        return envelope(_apply_or_404(service.pause, project_id))

    @router.post("/projects/{project_id}/resume", response_model=Envelope[ProjectManifest])
    def resume_project(project_id: UUID) -> Envelope[ProjectManifest]:
        return envelope(_apply_or_404(service.resume, project_id))

    @router.get("/system/disk", response_model=Envelope[DiskStatus])
    def disk_status() -> Envelope[DiskStatus]:
        return envelope(DiskStatus.model_validate(service.disk_status()))

    return router


def _get_or_404(service: ProjectService, project_id: UUID) -> ProjectManifest:
    return _apply_or_404(service.get, project_id)


def _apply_or_404(
    operation: Callable[[UUID], ProjectManifest], project_id: UUID
) -> ProjectManifest:
    try:
        return operation(project_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="project not found") from error
