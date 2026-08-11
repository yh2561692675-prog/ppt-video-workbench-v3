import json
import os
import shutil
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

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

from workbench.api.assets import create_assets_router
from workbench.api.audio import create_audio_router
from workbench.api.confirmations import create_confirmations_router
from workbench.api.continuity import create_continuity_router
from workbench.api.diagnostics import create_diagnostics_router
from workbench.api.effects import create_effects_router
from workbench.api.environment import create_environment_router
from workbench.api.export_presets import create_export_presets_router
from workbench.api.fidelity import create_fidelity_router
from workbench.api.heygen_settings import create_heygen_settings_router
from workbench.api.jobs import create_jobs_router
from workbench.api.matching import create_matching_router
from workbench.api.material_collections import create_material_collections_router
from workbench.api.materials import create_materials_router
from workbench.api.migrations import create_migrations_router, load_raw_project
from workbench.api.narrations import create_narrations_router
from workbench.api.peripheral import create_peripheral_router
from workbench.api.peripheral_s1 import create_peripheral_s1_router
from workbench.api.preflight import create_preflight_router
from workbench.api.presenter import create_presenter_router
from workbench.api.projects import create_projects_router
from workbench.api.quality import create_quality_router
from workbench.api.scheduler import create_scheduler_router
from workbench.api.secure_updates import create_secure_updates_router
from workbench.api.settings import create_settings_router
from workbench.api.sources import create_sources_router
from workbench.api.storage import create_storage_router
from workbench.api.subtitle_workbench import create_subtitle_workbench_router
from workbench.api.subtitles import create_subtitle_router
from workbench.api.timeline_production import TimelineWorkspaceService, create_timeline_router
from workbench.api.updates import create_updates_router
from workbench.api.video import create_video_router
from workbench.assets.service import AssetRegistryService
from workbench.audio.difference_service import DifferenceService
from workbench.audio.heygen_service import HeyGenService
from workbench.audio.importer import AudioImportService
from workbench.audio.models import WhisperModelManager
from workbench.audio.service import AudioService
from workbench.audio.timeline_service import TimelineService
from workbench.audio.transcriber import Transcriber, TranscriptionBackend
from workbench.audio.transcription_service import TranscriptionService
from workbench.cache.cleanup import CleanupService
from workbench.continuity.service import ContinuityService
from workbench.diagnostics.center import (
    DiagnosticCenter,
    DiagnosticCenterProtocol,
    UnavailableDiagnosticCenter,
)
from workbench.diagnostics.package import DiagnosticPackager
from workbench.diagnostics.probes import build_default_probes, create_heygen_health_probe
from workbench.domain.enums import JobType
from workbench.effects.service import EffectService
from workbench.environment.detector import EnvironmentDetector
from workbench.exports.presets import ExportPresetService
from workbench.fidelity.jobs import FidelityJobService
from workbench.fidelity.scanner import PptxFidelityScanner
from workbench.fidelity.static_renderer import build_static_previews
from workbench.integrations.heygen.client import HeyGenClient
from workbench.integrations.llm.client import LlmClient
from workbench.jobs.execution import PersistentRenderExecutionContext
from workbench.jobs.worker import RenderJobWorker
from workbench.materials.service import MaterialCollectionService
from workbench.media.presenter_audio import AnalysisAudio
from workbench.media.presenter_service import PresenterImportService, PresenterProbe
from workbench.narration.repository import NarrationRepository
from workbench.ocr.paddle_adapter import OcrEngine
from workbench.p2 import P2Composition, P2FeatureFlags
from workbench.peripheral_s1.coordinator import S1Coordinator
from workbench.peripheral_s1.inbox import ProjectionInbox
from workbench.peripheral_s1.projector import ProjectorRegistry
from workbench.preflight.engine import PreflightEngine, RuntimeProbe
from workbench.quality.jobs import QualityJobService
from workbench.rendering.export_pipeline import RenderGraphExportPipeline
from workbench.rendering.feature_flags import RenderFeatureFlags
from workbench.rendering.models import RenderGraphV2
from workbench.rendering.preflight import GraphPreflight
from workbench.rendering.preview_service import AuthoritativePreviewService
from workbench.rendering.project_reader import ProjectRenderSourceReader
from workbench.providers.upstream import (
    BrokerCompletionClient,
    BrokerOcrEngine,
    BrokerPageRenderer,
    BrokerSpeechSynthesizer,
    BrokerTranscriptionBackend,
    BuiltinHandler,
    create_llm_handler,
)
from workbench.runtime.layout import RuntimeComponentMissingError, RuntimeLayout
from workbench.scheduler.service import BatchSchedulerService
from workbench.services.import_service import ImportService
from workbench.services.matching_service import MatchingService
from workbench.services.material_processing_service import MaterialProcessingService
from workbench.services.narration_generation_service import NarrationGenerationService
from workbench.services.preflight_service import PreflightService
from workbench.services.presenter_analysis_service import PresenterAnalysisService
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
from workbench.subtitles.workbench_service import SubtitleWorkbenchService
from workbench.updates.secure import SecureUpdateClient, TrustedRoot
from workbench.updates.service import UpdateService
from workbench.video.models import PreflightIssue as VideoPreflightIssue
from workbench.video.models import VideoPreflight
from workbench.video.package_service import VideoExportService
from workbench.video.preview_service import VideoPreviewService
from workbench.video.props_service import VideoPropsService
from workbench.video.render_job import RenderJobService
from workbench.video.render_service import PageRenderer
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
    presenter_probe: PresenterProbe | None = None,
    presenter_audio_extractor: Callable[[Path, Path], AnalysisAudio] | None = None,
    p2_flags: P2FeatureFlags | None = None,
    provider_handlers: dict[str, BuiltinHandler] | None = None,
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
        worker = getattr(app.state, "render_job_worker", None)
        if worker is not None:
            worker.start()
        yield
        if worker is not None:
            worker.stop(timeout=10.0)
        service.close()

    app = FastAPI(title="PPT Video Workbench", version="0.1.0", lifespan=lifespan)
    app.state.project_service = service
    app.state.llm_profile_store = profile_store
    app.state.heygen_profile_store = heygen_profile_store
    audio_service = AudioService(configured_root)
    audio_gate = AudioGateService(audio_service)
    llm_client = LlmClient(transport=llm_transport)
    heygen_client = HeyGenClient(transport=heygen_transport)
    configured_provider_handlers: dict[str, BuiltinHandler] = {
        "builtin-llm": create_llm_handler(llm_client, profile_store)
    }
    if provider_handlers:
        configured_provider_handlers.update(provider_handlers)
    p2_composition = P2Composition.build(
        configured_root,
        flags=p2_flags,
        provider_handlers=configured_provider_handlers,
    )
    p2_composition.install(app)
    completion_factory: Callable[[UUID], BrokerCompletionClient] | None = None
    provider_broker = None
    artifact_store = None
    provider_tenant_id: UUID | None = None
    configured_transcription_backend = transcription_backend
    configured_ocr_engine = ocr_engine
    configured_video_renderer = video_renderer
    configured_speech_synthesizer = None
    if (
        p2_composition.provider_state is not None
        and p2_composition.provider_state.broker is not None
        and p2_composition.artifact_store is not None
    ):
        provider_broker = p2_composition.provider_state.broker
        artifact_store = p2_composition.artifact_store
        provider_tenant_id = uuid5(NAMESPACE_URL, configured_root.resolve().as_uri())

        def make_completion_client(profile_id: UUID) -> BrokerCompletionClient:
            return BrokerCompletionClient(
                provider_broker,
                artifact_store,
                tenant_id=provider_tenant_id,
                profile_id=profile_id,
            )

        completion_factory = make_completion_client
        if configured_transcription_backend is None:
            configured_transcription_backend = BrokerTranscriptionBackend(
                provider_broker, artifact_store, tenant_id=provider_tenant_id
            )
        if configured_ocr_engine is None:
            configured_ocr_engine = BrokerOcrEngine(
                provider_broker, artifact_store, tenant_id=provider_tenant_id
            )
        if configured_video_renderer is None:
            configured_video_renderer = BrokerPageRenderer(
                provider_broker, artifact_store, tenant_id=provider_tenant_id
            )
        configured_speech_synthesizer = BrokerSpeechSynthesizer(
            provider_broker, artifact_store, tenant_id=provider_tenant_id
        )
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
                    render_worker_alive=lambda: bool(
                        getattr(
                            getattr(app.state, "render_job_worker", None),
                            "is_alive",
                            False,
                        )
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
    subtitle_workbench_service = SubtitleWorkbenchService(
        configured_root,
        project_dir_resolver=lambda project_id: service.get(project_id).project_dir,
        projects=service,
        legacy_getter=subtitle_service.get,
    )
    app.state.subtitle_workbench_service = subtitle_workbench_service
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
        renderer=configured_video_renderer,
        preflight_gate=preflight_service.render_gate,
    )
    quality_job_service = QualityJobService(
        configured_root,
        project_dir_resolver=lambda project_id: service.get(project_id).project_dir,
    )
    asset_registry_service = AssetRegistryService(
        configured_root,
        project_dir_resolver=lambda project_id: service.get(project_id).project_dir,
        jobs=service.jobs,
    )
    app.state.asset_registry_service = asset_registry_service
    material_collection_service = MaterialCollectionService(
        configured_root,
        project_dir_resolver=lambda project_id: service.get(project_id).project_dir,
    )
    app.state.material_collection_service = material_collection_service
    continuity_service = ContinuityService(
        configured_root,
        project_dir_resolver=lambda project_id: service.get(project_id).project_dir,
        projects=service,
    )
    app.state.continuity_service = continuity_service
    export_preset_service = ExportPresetService(
        configured_root,
        project_dir_resolver=lambda project_id: service.get(project_id).project_dir,
        projects=service,
    )
    app.state.export_preset_service = export_preset_service
    batch_scheduler_service = BatchSchedulerService(
        configured_root,
        project_dir_resolver=lambda project_id: service.get(project_id).project_dir,
        repository=service.jobs,
        preset_exists=lambda preset_id: any(
            preset.id == preset_id for preset in export_preset_service.presets()
        ),
    )
    app.state.batch_scheduler_service = batch_scheduler_service
    app.state.quality_job_service = quality_job_service
    fidelity_job_service = FidelityJobService(
        configured_root,
        scanner=PptxFidelityScanner(static_renderer=build_static_previews),
        project_dir_resolver=lambda project_id: service.get(project_id).project_dir,
    )
    timeline_workspace_service = TimelineWorkspaceService(
        configured_root,
        project_dir_resolver=lambda project_id: service.get(project_id).project_dir,
    )
    authoritative_preview_service = AuthoritativePreviewService(service)
    app.state.fidelity_job_service = fidelity_job_service
    app.state.timeline_workspace_service = timeline_workspace_service
    app.state.authoritative_preview_service = authoritative_preview_service
    app.state.video_export_service = video_export_service
    render_feature_flags = RenderFeatureFlags.from_environment()

    def compatibility_video_preflight(project_id: UUID) -> VideoPreflight | None:
        root, payload = load_raw_project(service, project_id)
        pointer = root / "07_视频工程" / "v2-migration.json"
        if not pointer.is_file():
            try:
                service.get(project_id)
                return None
            except (KeyError, ValueError):
                pass
        source = ProjectRenderSourceReader(root).open(
            payload,
            renderer_generation=render_feature_flags.renderer_generation,
            migration_enabled=render_feature_flags.compile,
        )
        if source.mode == "v2" and source.graph is not None:
            report = GraphPreflight().check(
                source.graph,
                root,
                strict_assets=render_feature_flags.strict_assets,
            )
            return VideoPreflight(
                allowed=report.allowed,
                issues=[
                    VideoPreflightIssue(
                        code=issue.code,
                        message=issue.message,
                        action=issue.action,
                        blocking=issue.blocking,
                    )
                    for issue in report.issues
                ],
            )
        if source.legacy is None:
            return None
        return VideoPreflight(
            allowed=not any(issue.severity == "blocking" for issue in source.legacy.issues),
            issues=[
                VideoPreflightIssue(
                    code=issue.code,
                    message=issue.message,
                    action="Review the legacy migration preview before export.",
                    blocking=issue.severity == "blocking",
                )
                for issue in source.legacy.issues
            ],
        )

    def render_graph_provider(project_id: UUID) -> RenderGraphV2:
        return timeline_workspace_service.compile_v2(
            project_id,
            continuity=continuity_service.get(project_id),
            subtitles=subtitle_workbench_service.get(project_id),
            assets=asset_registry_service.list_assets(project_id),
        )

    def render_graph_exporter(
        project_id: UUID,
        graph: RenderGraphV2,
        context: PersistentRenderExecutionContext,
    ) -> dict[str, object]:
        project = service.get(project_id)
        root = (configured_root / project.project_dir).resolve()
        run_id = str(context.job_id or uuid4())
        staging = root / "08_输出" / ".render-graph-jobs" / run_id
        pipeline = RenderGraphExportPipeline(
            root,
            ffmpeg=(str(renderer_runtime.ffmpeg_executable) if renderer_runtime else "ffmpeg"),
        )
        result = pipeline.export(
            graph,
            staging,
            context=context,
            strict_assets=render_feature_flags.strict_assets,
        )
        output_root = root / "08_输出"
        output_root.mkdir(parents=True, exist_ok=True)
        published_video = output_root / "最终视频.mp4"
        shutil.copy2(result.video_path, published_video)
        package = output_root / "制作包"
        shutil.copytree(staging, package, dirs_exist_ok=True)
        return {
            "mp4_relative_path": published_video.relative_to(root).as_posix(),
            "package_relative_path": package.relative_to(root).as_posix(),
            "graph_hash": graph.graph_hash,
            "artifact_count": len(result.subtitle_artifacts) + 4,
        }

    app.state.render_feature_flags = render_feature_flags
    render_job_service = RenderJobService(
        service,
        video_preview_service,
        video_export_service,
        graph_provider=render_graph_provider,
        graph_exporter=render_graph_exporter,
        feature_flags=render_feature_flags,
    )
    render_job_worker = RenderJobWorker(
        service.jobs,
        render_job_service.handle,
        job_types=(
            JobType.EXPORT_PACKAGE,
            JobType.DERIVE_ASSET,
            JobType.BUILD_WAVEFORM,
            JobType.RENDER_PREVIEW,
        ),
        handlers={
            JobType.DERIVE_ASSET: asset_registry_service.handle_derivative_job,
            JobType.BUILD_WAVEFORM: asset_registry_service.handle_derivative_job,
            JobType.RENDER_PREVIEW: authoritative_preview_service.handle,
        },
        enabled=os.environ.get("WORKBENCH_ASYNC_RENDER_ENABLED", "true").lower()
        not in {"0", "false", "no"},
    )
    render_job_service.worker = render_job_worker
    app.state.async_render_enabled = render_job_worker.enabled
    app.state.render_job_service = render_job_service
    app.state.render_job_worker = render_job_worker
    app.state.effect_service = EffectService(service)
    app.state.preflight_service = preflight_service
    cleanup_service = CleanupService(service)
    app.state.cleanup_service = cleanup_service
    configured_environment_detector = environment_detector or EnvironmentDetector(configured_root)
    app.state.environment_detector = configured_environment_detector
    configured_update_service = update_service or UpdateService(configured_root)
    app.state.update_service = configured_update_service
    secure_update_client = _build_secure_update_client(configured_root)
    app.state.secure_update_client = secure_update_client
    configured_peripheral_client = peripheral_client or create_peripheral_client(
        WorkbenchPeripheralSettings.from_env()
    )
    app.state.peripheral_client = configured_peripheral_client
    s1_coordinator = S1Coordinator(
        workspace_root=configured_root,
        adapter=configured_peripheral_client,
        inbox=ProjectionInbox(service.database),
        projector=ProjectorRegistry(),
        database=service.database,
        project_dir_resolver=lambda project_id: (
            configured_root / service.get(project_id).project_dir
        ),
    )
    app.state.s1_coordinator = s1_coordinator
    app.include_router(
        create_projects_router(
            service,
            audio_gate.can_enter_subtitles,
            preflight_service.can_enter_render,
        )
    )
    app.include_router(create_effects_router(app.state.effect_service))
    presenter_models = WhisperModelManager(configured_root / "settings" / "asr-models")
    app.include_router(
        create_presenter_router(
            PresenterImportService(service, presenter_probe),
            PresenterAnalysisService(
                service,
                backend=transcription_backend,
                models=presenter_models,
                audio_extractor=presenter_audio_extractor,
            ),
        )
    )
    transcriber = Transcriber(
        presenter_models,
        configured_transcription_backend,
    )
    app.include_router(
        create_audio_router(
            AudioImportService(service),
            TranscriptionService(service, transcriber),
            DifferenceService(service),
            TimelineService(service),
            HeyGenService(
                service,
                heygen_profile_store,
                heygen_client,
                speech_synthesizer=configured_speech_synthesizer,
            ),
            service,
            audio_gate,
        )
    )
    app.include_router(create_subtitle_router(subtitle_service))
    app.include_router(create_subtitle_workbench_router(subtitle_workbench_service))
    app.include_router(
        create_video_router(
            video_preview_service,
            video_export_service,
            render_job_service,
            compatibility_video_preflight,
        )
    )
    app.include_router(create_quality_router(quality_job_service))
    app.include_router(create_jobs_router(service))
    app.include_router(create_migrations_router(service))
    app.include_router(create_assets_router(asset_registry_service))
    app.include_router(create_material_collections_router(material_collection_service))
    app.include_router(create_continuity_router(continuity_service))
    app.include_router(create_export_presets_router(export_preset_service))
    app.include_router(create_scheduler_router(batch_scheduler_service))
    app.include_router(create_fidelity_router(fidelity_job_service))
    app.include_router(
        create_timeline_router(timeline_workspace_service, authoritative_preview_service)
    )
    app.include_router(create_preflight_router(preflight_service, video_export_service))
    app.include_router(create_sources_router(ImportService(service)))
    app.include_router(create_matching_router(MatchingService(service)))
    app.include_router(
        create_materials_router(MaterialProcessingService(service, ocr=configured_ocr_engine))
    )
    app.include_router(
        create_narrations_router(
            narration_repository,
            NarrationGenerationService(
                service,
                profile_store,
                llm_client,
                narration_repository,
                completion_factory=completion_factory,
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
    if secure_update_client is not None:
        app.include_router(create_secure_updates_router(secure_update_client))
    app.include_router(create_peripheral_router(configured_peripheral_client))
    app.include_router(create_peripheral_s1_router(configured_peripheral_client, s1_coordinator))

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
            details = {
                key: value
                for key, value in detail.items()
                if key not in {"code", "message", "action"}
            }
        else:
            action = "请检查输入后重试"
            details = None
        return _error_response(
            error.status_code,
            code=code,
            message=message,
            action=action,
            details=details,
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


def _build_secure_update_client(workspace_root: Path) -> SecureUpdateClient | None:
    root_path = os.environ.get("WORKBENCH_UPDATE_TRUST_ROOT")
    if not root_path:
        return None
    try:
        trusted_root = TrustedRoot.model_validate(
            json.loads(Path(root_path).read_text(encoding="utf-8"))
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return SecureUpdateClient(workspace_root, trusted_root=trusted_root)


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
    details: dict[str, object] | None = None,
) -> JSONResponse:
    error_payload: dict[str, object] = {
        "code": code,
        "message": message,
        "action": action,
        "blocking": True,
        "page_id": None,
        "job_id": None,
    }
    if details:
        error_payload.update(details)
    return JSONResponse(
        status_code=status_code,
        content={
            "data": None,
            "error": error_payload,
            "request_id": str(uuid4()),
        },
    )


app = create_app()
