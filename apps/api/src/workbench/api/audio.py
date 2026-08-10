from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict

from workbench.api.projects import Envelope, envelope
from workbench.audio.alignment import BoundaryConflict, BoundaryRejected
from workbench.audio.difference_service import DifferenceService
from workbench.audio.ffmpeg import AudioNormalizationError
from workbench.audio.heygen_service import (
    HeyGenRegenerationRequired,
    HeyGenRouteSwitchRequired,
    HeyGenService,
)
from workbench.audio.importer import AudioImportError, AudioImportService
from workbench.audio.models import Transcript
from workbench.audio.timeline_service import TimelineService
from workbench.audio.transcriber import (
    ModelUnavailable,
    TranscriptionError,
    available_transcription_devices,
)
from workbench.audio.transcription_service import TranscriptionService
from workbench.domain.audio import AudioAsset, AudioDifference, AudioImportRecord, AudioTimeline
from workbench.domain.confirmation import GateResult
from workbench.integrations.heygen.client import HeyGenIntegrationError
from workbench.services.project_service import ProjectService
from workbench.workflow.audio_gate import AudioGateService


class DifferenceResolve(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution: Literal["accept_recording", "change_narration", "reimport"]


class TimelineBoundaryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    time_ms: int
    version: int


class TranscriptionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device: Literal["cpu", "cuda"] = "cpu"


class HeyGenSynthesisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: UUID
    revision_id: UUID
    voice_id: str
    speed: float = 1
    replace_existing: bool = False


def create_audio_router(
    service: AudioImportService,
    transcription: TranscriptionService,
    differences: DifferenceService,
    timeline: TimelineService,
    heygen: HeyGenService,
    projects: ProjectService,
    audio_gate: AudioGateService,
) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}/audio")

    @router.get("/gate", response_model=Envelope[GateResult])
    def subtitle_gate(project_id: UUID) -> Envelope[GateResult]:
        try:
            return envelope(audio_gate.can_enter_subtitles(projects.get(project_id)))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error

    @router.post(
        "/import", status_code=status.HTTP_201_CREATED, response_model=Envelope[AudioImportRecord]
    )
    async def import_audio(
        project_id: UUID, file: Annotated[UploadFile, File()]
    ) -> Envelope[AudioImportRecord]:
        try:
            return envelope(
                service.import_bytes(
                    project_id, file.filename or "recording.wav", await file.read()
                )
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except AudioImportError as error:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "audio_import_rejected",
                    "message": str(error),
                    "action": "请检查录音文件后重新导入",
                },
            ) from error

    @router.post(
        "/transcribe", status_code=status.HTTP_201_CREATED, response_model=Envelope[Transcript]
    )
    def transcribe_audio(
        project_id: UUID, request: TranscriptionRequest | None = None
    ) -> Envelope[Transcript]:
        try:
            device = request.device if request else "cpu"
            return envelope(transcription.transcribe_project(project_id, device=device))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except (ValueError, ModelUnavailable, TranscriptionError) as error:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "audio_transcription_rejected",
                    "message": str(error),
                    "action": "请检查本地模型与规范化录音后重试",
                },
            ) from error

    @router.get("/transcription-devices", response_model=Envelope[list[str]])
    def transcription_devices() -> Envelope[list[str]]:
        return envelope(available_transcription_devices())

    @router.post("/differences/compare", response_model=Envelope[list[AudioDifference]])
    def compare_differences(project_id: UUID) -> Envelope[list[AudioDifference]]:
        try:
            return envelope(differences.compare_project(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "audio_difference_rejected",
                    "message": str(error),
                    "action": "请先完成旁白确认与本地转写",
                },
            ) from error

    @router.patch("/differences/{difference_id}", response_model=Envelope[AudioDifference])
    def resolve_difference(
        project_id: UUID, difference_id: UUID, request: DifferenceResolve
    ) -> Envelope[AudioDifference]:
        try:
            return envelope(differences.resolve(project_id, difference_id, request.resolution))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="difference not found") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post("/timeline/build", response_model=Envelope[AudioTimeline])
    def build_timeline(project_id: UUID) -> Envelope[AudioTimeline]:
        try:
            return envelope(timeline.build(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="project not found") from error
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.patch("/timeline/{boundary_id}", response_model=Envelope[AudioTimeline])
    def change_timeline_boundary(
        project_id: UUID, boundary_id: UUID, request: TimelineBoundaryUpdate
    ) -> Envelope[AudioTimeline]:
        try:
            return envelope(
                timeline.change_boundary(project_id, boundary_id, request.time_ms, request.version)
            )
        except BoundaryConflict as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "timeline_version_conflict",
                    "message": str(error),
                    "action": "请刷新时间轴后重新调整",
                },
            ) from error
        except KeyError as error:
            raise HTTPException(status_code=404, detail="timeline boundary not found") from error
        except (ValueError, BoundaryRejected) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post(
        "/heygen/{page_id}",
        status_code=status.HTTP_201_CREATED,
        response_model=Envelope[AudioAsset],
    )
    def synthesize_heygen_page(
        project_id: UUID,
        page_id: UUID,
        request: HeyGenSynthesisRequest,
        response: Response,
    ) -> Envelope[AudioAsset]:
        try:
            asset = heygen.synthesize_page(
                project_id,
                page_id,
                request.revision_id,
                request.voice_id,
                request.profile_id,
                speed=request.speed,
                replace_existing=request.replace_existing,
            )
            if asset.cached:
                response.status_code = status.HTTP_200_OK
            return envelope(asset)
        except HeyGenRegenerationRequired as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "heygen_regeneration_confirmation_required",
                    "message": str(error),
                    "action": "请明确确认更换声音后再生成",
                },
            ) from error
        except HeyGenRouteSwitchRequired as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "audio_route_switch_required",
                    "message": str(error),
                    "action": "请先完成项目级音频路线切换，再生成 HeyGen 页面",
                },
            ) from error
        except KeyError as error:
            raise HTTPException(
                status_code=404, detail="project, page or profile not found"
            ) from error
        except (ValueError, AudioNormalizationError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except HeyGenIntegrationError as error:
            raise HTTPException(
                status_code=422,
                detail={"code": error.code, "message": str(error), "action": error.action},
            ) from error

    return router
