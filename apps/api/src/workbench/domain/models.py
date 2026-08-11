from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workbench.audio.models import Transcript

from .audio import AudioDifference, AudioImportRecord, AudioTimeline, SubtitleArtifact
from .confirmation import Confirmation
from .effects import EffectPlanRecord, EffectProjectPolicy
from .enums import JobStatus, JobType, NodeStatus
from .errors import UnsupportedManifestVersion
from .extraction import PageExtraction
from .issues import CleanupPlanRecord, IssueConfirmation, PreflightReport
from .matching import PageMatch
from .presenter import PresentationMode, PresenterSource, PresenterTimelineV1
from .source_file import SourceFile


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CacheKey(ContractModel):
    source_hash: str
    content_version: str
    template_version: str | None = None
    audio_source: str | None = None
    timeline_version: str | None = None


class NarrationRecord(ContractModel):
    id: UUID
    revision_id: UUID
    text: str = ""
    status: NodeStatus = NodeStatus.NOT_STARTED
    confirmed_revision_id: UUID | None = None
    author: str = "system"
    version: int = Field(default=1, ge=1)
    source_refs: list[str] = Field(default_factory=list)
    insufficiencies: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class AudioRecord(ContractModel):
    id: UUID
    status: NodeStatus = NodeStatus.NOT_STARTED
    source: Literal["local", "heygen"]
    relative_path: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    cache_key: str | None = None
    narration_revision_id: UUID | None = None
    voice_id: str | None = None
    remote_request_id: str | None = None


class TimelineRecord(ContractModel):
    id: UUID
    status: NodeStatus = NodeStatus.NOT_STARTED
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> TimelineRecord:
        if self.end_ms < self.start_ms:
            raise ValueError("timeline end must not precede start")
        return self


class RenderRecord(ContractModel):
    id: UUID
    status: NodeStatus = NodeStatus.NOT_STARTED
    relative_path: str | None = None
    cache_key: CacheKey | None = None


class VideoPreflightRecord(ContractModel):
    id: UUID
    allowed: bool
    issue_codes: list[str] = Field(default_factory=list)
    props_cache_key: str | None = None
    reduced_motion: bool = False
    checked_at: datetime


class VideoExportRecord(ContractModel):
    id: UUID
    status: NodeStatus = NodeStatus.COMPLETED
    mp4_relative_path: str | None = None
    package_relative_path: str | None = None
    duration_ms: int = Field(ge=0)
    artifact_count: int = Field(ge=0)
    error_code: str | None = None
    exported_at: datetime


class PageRecord(ContractModel):
    id: UUID
    order: int = Field(ge=1)
    title: str | None = None
    status: NodeStatus = NodeStatus.NOT_STARTED
    source_file_id: UUID | None = None
    narration: NarrationRecord | None = None
    audio: AudioRecord | None = None
    timeline: TimelineRecord | None = None
    render: RenderRecord | None = None
    effect_plan: EffectPlanRecord | None = None


class JobRecord(ContractModel):
    schema_version: Literal["1.0"] = "1.0"
    id: UUID
    project_id: UUID
    job_type: JobType
    status: JobStatus = JobStatus.QUEUED
    cache_key: str
    page_id: UUID | None = None
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    attempts: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1)
    paid: bool = False
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    input_fingerprint: str | None = None
    idempotency_key: str | None = None
    parent_job_id: UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | None = None
    stage: str = "queued"
    message: str = ""
    error_code: str | None = None
    revision: int = Field(default=1, ge=1)
    priority: int = Field(default=0, ge=-100, le=100)
    current_attempt_id: UUID | None = None
    heartbeat_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_status(cls, value: Any) -> Any:
        if isinstance(value, dict):
            migrated = dict(value)
            migrated["status"] = {
                "not_started": JobStatus.QUEUED.value,
                "completed": JobStatus.SUCCEEDED.value,
            }.get(str(migrated.get("status")), migrated.get("status", JobStatus.QUEUED.value))
            return migrated
        return value


class AuditEvent(ContractModel):
    action: str
    occurred_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class LlmUsageRecord(ContractModel):
    profile_id: UUID
    base_url_digest: str
    model: str
    used_at: datetime


class ProjectManifest(ContractModel):
    schema_version: Literal[1] = 1
    id: UUID
    name: str = Field(min_length=1, max_length=120)
    project_dir: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime
    current_step: int = Field(default=1, ge=1, le=7)
    status: NodeStatus = NodeStatus.NOT_STARTED
    pages: list[PageRecord] = Field(default_factory=list)
    jobs: list[JobRecord] = Field(default_factory=list)
    source_files: list[SourceFile] = Field(default_factory=list)
    audit_log: list[AuditEvent] = Field(default_factory=list)
    matches: list[PageMatch] = Field(default_factory=list)
    page_extractions: list[PageExtraction] = Field(default_factory=list)
    material_cache_key: str | None = None
    outline_artifact_path: str | None = None
    narration_confirmations: list[Confirmation] = Field(default_factory=list)
    llm_usage: list[LlmUsageRecord] = Field(default_factory=list)
    audio_import: AudioImportRecord | None = None
    transcript: Transcript | None = None
    audio_differences: list[AudioDifference] = Field(default_factory=list)
    audio_timeline: AudioTimeline | None = None
    subtitle_artifact: SubtitleArtifact | None = None
    video_preflight: VideoPreflightRecord | None = None
    video_export: VideoExportRecord | None = None
    preflight_report: PreflightReport | None = None
    preflight_history: list[str] = Field(default_factory=list)
    issue_confirmations: list[IssueConfirmation] = Field(default_factory=list)
    cleanup_plans: list[CleanupPlanRecord] = Field(default_factory=list)
    effect_policy: EffectProjectPolicy = Field(default_factory=EffectProjectPolicy)
    presentation_mode: PresentationMode = PresentationMode.AI_NARRATION
    presenter_source: PresenterSource | None = None
    presenter_timeline: PresenterTimelineV1 | None = None

    @model_validator(mode="after")
    def validate_page_identity(self) -> ProjectManifest:
        page_ids = [page.id for page in self.pages]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("duplicate page id")
        orders = [page.order for page in self.pages]
        if len(orders) != len(set(orders)):
            raise ValueError("duplicate page order")
        if (
            self.presentation_mode is PresentationMode.HUMAN_PRESENTER
            and self.presenter_source is None
        ):
            raise ValueError("human_presenter requires presenter_source")
        if self.presenter_timeline is not None:
            if self.presenter_source is None:
                raise ValueError("presenter_timeline requires presenter_source")
            if self.presenter_timeline.source_id != self.presenter_source.id:
                raise ValueError("presenter_timeline source does not match presenter_source")
            if self.presenter_timeline.source_version != self.presenter_source.sha256:
                raise ValueError("presenter_timeline source version is stale")
        return self


class ProblemDetails(ContractModel):
    code: str
    message: str
    action: str
    blocking: bool
    page_id: UUID | None = None
    job_id: UUID | None = None


def stable_page_id(project_id: UUID, order: int) -> UUID:
    if order < 1:
        raise ValueError("page order must be positive")
    return uuid5(project_id, f"page:{order}")


def validate_manifest(payload: dict[str, Any]) -> ProjectManifest:
    return ProjectManifest.model_validate(payload)


def migrate_manifest(payload: dict[str, Any], target_version: int) -> dict[str, Any]:
    if target_version != 1:
        raise UnsupportedManifestVersion(f"Unsupported target schema version: {target_version}")
    source_version = payload.get("schema_version")
    if source_version == 1:
        return deepcopy(payload)
    if source_version != 0:
        raise UnsupportedManifestVersion(f"Unsupported source schema version: {source_version}")

    migrated = deepcopy(payload)
    project_id = UUID(str(migrated["id"]))
    created_at = migrated["created_at"]
    pages = []
    for index, page in enumerate(migrated.get("pages", []), start=1):
        migrated_page = dict(page)
        order = int(migrated_page.get("order", index))
        migrated_page.setdefault("id", str(stable_page_id(project_id, order)))
        migrated_page.setdefault("order", order)
        migrated_page.setdefault("status", NodeStatus.NOT_STARTED.value)
        pages.append(migrated_page)

    return {
        "schema_version": 1,
        "id": str(project_id),
        "name": migrated["project_name"],
        "project_dir": migrated["path"],
        "created_at": created_at,
        "updated_at": migrated.get("updated_at", created_at),
        "current_step": migrated.get("current_step", 1),
        "status": migrated.get("status", NodeStatus.NOT_STARTED.value),
        "pages": pages,
        "jobs": migrated.get("jobs", []),
        "source_files": migrated.get("source_files", []),
        "audit_log": migrated.get("audit_log", []),
        "matches": migrated.get("matches", []),
        "page_extractions": migrated.get("page_extractions", []),
        "material_cache_key": migrated.get("material_cache_key"),
        "outline_artifact_path": migrated.get("outline_artifact_path"),
        "narration_confirmations": migrated.get("narration_confirmations", []),
        "llm_usage": migrated.get("llm_usage", []),
        "audio_import": migrated.get("audio_import"),
        "transcript": migrated.get("transcript"),
        "audio_differences": migrated.get("audio_differences", []),
        "audio_timeline": migrated.get("audio_timeline"),
        "subtitle_artifact": migrated.get("subtitle_artifact"),
        "video_preflight": migrated.get("video_preflight"),
        "video_export": migrated.get("video_export"),
        "presentation_mode": migrated.get("presentation_mode", "ai_narration"),
        "presenter_source": migrated.get("presenter_source"),
        "presenter_timeline": migrated.get("presenter_timeline"),
    }
