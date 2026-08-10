import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope
from workbench_peripheral_adapter import (
    PeripheralClientProtocol,
    create_peripheral_client,
)

from workbench.api.audio import create_audio_router
from workbench.api.confirmations import create_confirmations_router
from workbench.api.diagnostics import create_diagnostics_router
from workbench.api.effects import create_effects_router
from workbench.api.environment import create_environment_router
from workbench.api.heygen_settings import create_heygen_settings_router
from workbench.api.matching import create_matching_router
from workbench.api.materials import create_materials_router
from workbench.api.narrations import create_narrations_router
from workbench.api.peripheral import create_peripheral_router
from workbench.api.preflight import create_preflight_router
from workbench.api.projects import create_projects_router
from workbench.api.settings import create_settings_router
from workbench.api.sources import create_sources_router
from workbench.api.storage import create_storage_router
from workbench.api.subtitles import create_subtitle_router
from workbench.api.updates import create_updates_router
from workbench.api.video import create_video_router
from workbench.audio.difference_service import DifferenceService
from workbench.audio.heygen_service import HeyGenService
from workbench.audio.importer import AudioImportService
from workbench.audio.models import WhisperModelManager
from workbench.audio.service import AudioService
from workbench.audio.timeline_service import TimelineService
from workbench.audio.transcriber import Transcriber, TranscriptionBackend
from workbench.audio.transcription_service import TranscriptionService
from workbench.cache.cleanup import CleanupService
from workbench.diagnostics.center import (
    DiagnosticCenter,
    DiagnosticCenterProtocol,
    UnavailableDiagnosticCenter,
)
from workbench.diagnostics.package import DiagnosticPackager
from workbench.diagnostics.probes import build_default_probes, create_heygen_health_probe
from workbench.environment.detector import EnvironmentDetector
from workbench.integrations.heygen.client import HeyGenClient
from workbench.integrations.llm.client import LlmClient
from workbench.narration.repository import NarrationRepository
from workbench.ocr.paddle_adapter import OcrEngine
from workbench.preflight.engine import PreflightEngine, RuntimeProbe
from workbench.runtime.layout import RuntimeComponentMissingError, RuntimeLayout
from workbench.services.import_service import ImportService
from workbench.services.matching_service import MatchingService
from workbench.services.material_processing_service import MaterialProcessingService
from workbench.services.narration_generation_service import NarrationGenerationService
from workbench.services.preflight_service import PreflightService
from workbench.services.project_service import ProjectService
from workbench.settings.heygen_store import HeyGenProfileStore
from workbench.settings.peripheral import WorkbenchPeripheralSettings
from workbench.settings.secret_store import (
    LlmProfileStore,
    SecretProtector,
    WindowsDpapiProtector,
)
from workbench.storage.project_paths import ProjectStorageRoots
from workbench.subtitles.service import SubtitleService
from workbench.updates.service import UpdateService
from workbench.video.package_service import VideoExportService
from workbench.video.preview_service import VideoPreviewService
from workbench.video.props_service import VideoPropsService
from workbench.video.render_service import PageRenderer
from workbench.effects.service import EffectService
from workbench.workflow.audio_gate import AudioGateService
from workbench.workflow.gates import NarrationGateService


class SinglePageStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as error:
            if error.status_code == 404 and path:
                return await super().get_response("index.html", scope)
            raise


def create_app(
    workspace_root: Path | None = None,
    *,
    diagnostic_root: Path | None = None,
    web_root: Path | None = None,
    ocr_engine: OcrEngine | None = None,
    secret_protector: SecretProtector | None = None,
    llm_transport: httpx.BaseTransport | None = None,
    transcription_backend: TranscriptionBackend | None = None,
    heygen_transport: httpx.BaseTransport | None = None,
    video_renderer: PageRenderer | None = None,
    preflight_runtime_probe: RuntimeProbe | None = None,
    environment_detector: EnvironmentDetector | None = None,
    update_service: UpdateService | None = None,
    peripheral_client: PeripheralClientProtocol | None = None,
    diagnostic_center_factory: Callable[[Path], DiagnosticCenterProtocol] | None = None,
) -> FastAPI:
    configured_root = workspace_root or Path(
        os.environ.get("WORKBENCH_WORKSPACE", Path.cwd() / "workspace-data")
    )
    configured_diagnostic_root = diagnostic_root or Path(
        os.environ.get("WORKBENCH_DIAGNOSTIC_ROOT", configured_root)
    )
    cache_root = os.environ.get("WORKBENCH_CACHE_ROOT")
    output_root = os.environ.get("WORKBENCH_OUTPUT_ROOT")
    storage_roots = (
        ProjectStorageRoots(Path(cache_root), Path(output_root))
        if cache_root and output_root
        else None
    )
    service = ProjectService(configured_root, storage_roots=storage_roots)
    profile_store = LlmProfileStore(
        configured_root / "settings" / "llm-profiles.json",
        secret_protector or WindowsDpapiProtector(),
    )
    heygen_profile_store = HeyGenProfileStore(
        configured_root / "settings" / "heygen-profiles.json",
        secret_protector or WindowsDpapiProtector(),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        service.close()

    app = FastAPI(title="PPT Video Workbench", version="0.1.0", lifespan=lifespan)
    app.state.project_service = service
    app.state.llm_profile_store = profile_store
    app.state.heygen_profile_store = heygen_profile_store
    audio_service = AudioService(configured_root)
    audio_gate = AudioGateService(audio_service)
    llm_client = LlmClient(transport=llm_transport)
    heygen_client = HeyGenClient(transport=heygen_transport)
    try:
        configured_diagnostic_center = (
            diagnostic_center_factory(configured_diagnostic_root)
            if diagnostic_center_factory is not None
            else DiagnosticCenter(
                configured_diagnostic_root,
                probes=build_default_probes(
                    configured_diagnostic_root,
                    heygen_probe=create_heygen_health_probe(
                        heygen_profile_store,
                        heygen_client,
                    ),
                ),
            )
        )
    except Exception as error:
        configured_diagnostic_center = UnavailableDiagnosticCenter(type(error).__name__)
    diagnostic_packager = DiagnosticPackager(
        configured_diagnostic_root,
        log_paths=_diagnostic_log_paths(configured_diagnostic_root),
        username=os.environ.get("USERNAME"),
    )
    app.state.diagnostic_center = configured_diagnostic_center
    narration_repository = NarrationRepository(service)
    subtitle_service = SubtitleService(service, audio_gate, audio_service)
    video_preview_service = VideoPreviewService(
        service, subtitle_service, VideoPropsService(audio_service)
    )
    try:
        renderer_runtime = RuntimeLayout.from_environment().require_renderer()
    except RuntimeComponentMissingError:
        renderer_runtime = None
    preflight_service = PreflightService(
        service,
        PreflightEngine(configured_root, runtime_probe=preflight_runtime_probe),
        video_preview_service,
    )
    video_export_service = VideoExportService(
        service,
        video_preview_service,
        ffmpeg=(str(renderer_runtime.ffmpeg_executable) if renderer_runtime else "ffmpeg"),
        ffprobe=(str(renderer_runtime.ffprobe_executable) if renderer_runtime else "ffprobe"),
        renderer=video_renderer,
        preflight_gate=preflight_service.render_gate,
    )
    app.state.video_export_service = video_export_service
    app.state.effect_service = EffectService(service)
    app.state.preflight_service = preflight_service
    cleanup_service = CleanupService(service)
    app.state.cleanup_service = cleanup_service
    configured_environment_detector = environment_detector or EnvironmentDetector(configured_root)
    app.state.environment_detector = configured_environment_detector
    configured_update_service = update_service or UpdateService(configured_root)
    app.state.update_service = configured_update_service
    configured_peripheral_client = peripheral_client or create_peripheral_client(
        WorkbenchPeripheralSettings.from_env()
    )
    app.state.peripheral_client = configured_peripheral_client
    app.include_router(
        create_projects_router(
            service,
            audio_gate.can_enter_subtitles,
            preflight_service.can_enter_render,
        )
    )
    app.include_router(create_effects_router(app.state.effect_service))
    transcriber = Transcriber(
        WhisperModelManager(configured_root / "settings" / "asr-models"),
        transcription_backend,
    )
    app.include_router(
        create_audio_router(
            AudioImportService(service),
            TranscriptionService(service, transcriber),
            DifferenceService(service),
            TimelineService(service),
            HeyGenService(service, heygen_profile_store, heygen_client),
            service,
            audio_gate,
        )
    )
    app.include_router(create_subtitle_router(subtitle_service))
    app.include_router(create_video_router(video_preview_service, video_export_service))
    app.include_router(create_preflight_router(preflight_service, video_export_service))
    app.include_router(create_sources_router(ImportService(service)))
    app.include_router(create_matching_router(MatchingService(service)))
    app.include_router(create_materials_router(MaterialProcessingService(service, ocr=ocr_engine)))
    app.include_router(
        create_narrations_router(
            narration_repository,
            NarrationGenerationService(
                service,
                profile_store,
                llm_client,
                narration_repository,
            ),
        )
    )
    app.include_router(create_confirmations_router(NarrationGateService(service)))
    app.include_router(create_settings_router(profile_store, llm_client))
    app.include_router(create_heygen_settings_router(heygen_profile_store, heygen_client))
    app.include_router(create_storage_router(cleanup_service))
    app.include_router(create_environment_router(configured_environment_detector))
    app.include_router(create_diagnostics_router(configured_diagnostic_center, diagnostic_packager))
    app.include_router(create_updates_router(configured_update_service))
    app.include_router(create_peripheral_router(configured_peripheral_client))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, __: RequestValidationError) -> JSONResponse:
        return _error_response(
            422,
            code="validation_error",
            message="请求参数不符合接口契约",
            action="请检查标出的字段后重试",
        )

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, error: HTTPException) -> JSONResponse:
        if error.status_code == 404:
            return _error_response(
                404,
                code="project_not_found",
                message="未找到指定项目",
                action="请返回项目中心重新选择",
            )
        detail = error.detail
        code = "request_rejected"
        message = str(detail)
        if isinstance(detail, dict):
            code = str(detail.get("code", code))
            message = str(detail.get("message", message))
            action = str(detail.get("action", "请检查输入后重试"))
        else:
            action = "请检查输入后重试"
        return _error_response(
            error.status_code,
            code=code,
            message=message,
            action=action,
        )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    configured_web_root = web_root or Path(os.environ.get("WORKBENCH_WEB_ROOT", ""))
    if (configured_web_root / "index.html").is_file():
        app.mount(
            "/",
            SinglePageStaticFiles(directory=configured_web_root, html=True),
            name="workbench-web",
        )

    return app


def _diagnostic_log_paths(workspace_root: Path) -> tuple[Path, ...]:
    candidates = [workspace_root / "logs" / "workbench.log"]
    configured = os.environ.get("WORKBENCH_LOG_ROOT")
    if configured:
        root = Path(configured)
        if root.is_file():
            candidates.append(root)
        elif root.is_dir():
            candidates.extend(sorted(root.glob("*.log"))[-10:])
    return tuple(path for path in candidates if path.is_file())


def _error_response(
    status_code: int,
    *,
    code: str,
    message: str,
    action: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "data": None,
            "error": {
                "code": code,
                "message": message,
                "action": action,
                "blocking": True,
                "page_id": None,
                "job_id": None,
            },
            "request_id": str(uuid4()),
        },
    )


app = create_app()
