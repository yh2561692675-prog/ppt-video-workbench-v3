from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workbench.assets.models import LicenseRecord


class RenderModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GraphCanvas(RenderModel):
    width: int = Field(gt=0, le=16_384)
    height: int = Field(gt=0, le=16_384)
    fps: int | None = Field(default=None, gt=0, le=240)
    fps_num: int | None = Field(default=None, gt=0, le=1_000_000)
    fps_den: int = Field(default=1, gt=0, le=1_000_000)
    duration_us: int = Field(default=0, ge=0)
    background: str = Field(default="#000000", min_length=1, max_length=32)
    pixel_format: str = "yuv420p"
    aspect_ratio: str = "16:9"

    @model_validator(mode="after")
    def normalize_fps(self) -> GraphCanvas:
        if self.fps is None and self.fps_num is None:
            raise ValueError("canvas requires fps or fps_num")
        if self.fps_num is None:
            object.__setattr__(self, "fps_num", self.fps)
        if self.fps is None:
            object.__setattr__(self, "fps", self.fps_num)
        return self


class MediaProbeMetadata(RenderModel):
    """Metadata observed from the media container/streams at compile time."""

    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    duration_us: int | None = Field(default=None, ge=0)
    fps_num: int | None = Field(default=None, gt=0)
    fps_den: int | None = Field(default=None, gt=0)


class ResolvedAsset(RenderModel):
    asset_id: UUID | None = None
    revision: int | None = Field(default=None, ge=1)
    project_id: UUID | None = None
    kind: str
    source_ref: str = Field(min_length=1)
    object_relative_path: str | None = Field(default=None, min_length=1)
    proxy_relative_path: str | None = Field(default=None, min_length=1)
    resolved_path: str | None = None
    mime_type: str | None = Field(default=None, min_length=1)
    content_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    exists: bool = False
    size_bytes: int | None = Field(default=None, ge=0)
    duration_us: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    fps_num: int | None = Field(default=None, gt=0)
    fps_den: int | None = Field(default=None, gt=0)
    media_probe: MediaProbeMetadata | None = None
    media_probe_status: Literal["not_requested", "verified", "failed", "unavailable"] = (
        "not_requested"
    )
    media_probe_error: str | None = Field(default=None, min_length=1)
    legacy_snapshot: bool = False
    alpha_mode: Literal["none", "straight", "premultiplied"] = "none"
    license_status: str = "unknown"
    license_expires_at: datetime | None = None
    license_snapshot: LicenseRecord | None = None

    @model_validator(mode="after")
    def normalize_paths_and_license(self) -> ResolvedAsset:
        if self.object_relative_path is None and self.resolved_path is not None:
            object.__setattr__(self, "object_relative_path", self.resolved_path)
        return self


class RenderNodeV2(RenderModel):
    id: UUID = Field(default_factory=uuid4)
    clip_id: UUID | None = None
    track_id: UUID | None = None
    kind: str
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    start_frame: int | None = Field(default=None, ge=0)
    end_frame_exclusive: int | None = Field(default=None, gt=0)
    track_order: int | None = Field(default=None, ge=0)
    source_in_us: int = Field(default=0, ge=0)
    source_ref: str = Field(min_length=1)
    asset_id: UUID | None = None
    asset_revision: int | None = Field(default=None, ge=1)
    z_index: int = 0
    blend_mode: str = "normal"
    opacity: float = Field(default=1, ge=0, le=1)
    cache_key: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    payload: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_range(self) -> RenderNodeV2:
        if self.end_us <= self.start_us:
            raise ValueError("render node end must be later than start")
        if (
            self.start_frame is not None
            and self.end_frame_exclusive is not None
            and self.end_frame_exclusive <= self.start_frame
        ):
            raise ValueError("render node end frame must be later than start frame")
        return self


class TransitionEdge(RenderModel):
    id: UUID = Field(default_factory=uuid4)
    from_node_id: UUID
    to_node_id: UUID
    kind: Literal["cut", "dissolve", "wipe", "slide", "match"] = "cut"
    start_us: int = Field(ge=0)
    end_us: int = Field(ge=0)
    duration_us: int | None = Field(default=None, ge=0)
    easing: Literal["linear", "ease_in", "ease_out", "ease_in_out"] = "ease_in_out"
    audio_mode: Literal["cut", "j_cut", "l_cut"] = "cut"
    audio_offset_us: int = 0
    chapter_boundary: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_range(self) -> TransitionEdge:
        if self.end_us < self.start_us:
            raise ValueError("transition end cannot precede start")
        if self.kind == "cut" and self.end_us != self.start_us:
            raise ValueError("cut transition must have zero duration")
        derived_duration = self.end_us - self.start_us
        if self.duration_us is None:
            object.__setattr__(self, "duration_us", derived_duration)
        elif self.duration_us != derived_duration:
            raise ValueError("transition duration must equal end_us - start_us")
        return self


class AudioMixClip(RenderModel):
    id: UUID = Field(default_factory=uuid4)
    kind: str
    source_ref: str = Field(min_length=1)
    asset_id: UUID | None = None
    asset_revision: int | None = Field(default=None, ge=1)
    timeline_start_us: int = Field(ge=0)
    timeline_end_us: int = Field(gt=0)
    source_in_us: int = Field(default=0, ge=0)
    source_duration_us: int | None = Field(default=None, ge=0)
    bus: Literal["narration", "presenter", "music", "sfx", "master"] = "narration"
    gain_db: float = 0
    fade_in_us: int = Field(default=0, ge=0)
    fade_out_us: int = Field(default=0, ge=0)
    pan: float = Field(default=0, ge=-1, le=1)

    @model_validator(mode="after")
    def validate_range(self) -> AudioMixClip:
        if self.timeline_end_us <= self.timeline_start_us:
            raise ValueError("audio clip end must be later than start")
        return self


class AudioDuckingRule(RenderModel):
    source_bus: str
    target_bus: str
    amount_db: float = Field(ge=0, le=60)
    attack_us: int = Field(default=50_000, ge=0)
    release_us: int = Field(default=200_000, ge=0)


class AudioMixPlan(RenderModel):
    clips: list[AudioMixClip] = Field(default_factory=list)
    ducking: list[AudioDuckingRule] = Field(default_factory=list)
    loudness_target_lufs: float = -16
    true_peak_db: float = -1


class SubtitleWord(RenderModel):
    text: str = Field(min_length=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)


class SubtitleCue(RenderModel):
    id: UUID = Field(default_factory=uuid4)
    language: str = Field(min_length=2, max_length=16)
    label: str = Field(min_length=1)
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    text: str = Field(min_length=1)
    translation: str | None = None
    words: list[SubtitleWord] = Field(default_factory=list)
    line_breaks: list[int] = Field(default_factory=list)
    style: dict[str, Any] = Field(default_factory=dict)
    track_id: UUID | None = None
    primary: bool = True
    visible: bool = True


class SubtitleRenderPlan(RenderModel):
    render_mode: Literal["burn_in", "soft", "both", "none"] = "soft"
    cues: list[SubtitleCue] = Field(default_factory=list)
    default_style: dict[str, Any] = Field(default_factory=dict)
    languages: list[str] = Field(default_factory=list)
    document_revision: int = Field(default=1, ge=1)
    document_hash: str = Field(default="0" * 64, pattern=r"^[0-9a-f]{64}$")
    tracks: list[dict[str, Any]] = Field(default_factory=list)


class AffectedRange(RenderModel):
    start_us: int = Field(ge=0)
    end_us: int = Field(gt=0)
    reasons: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_range(self) -> AffectedRange:
        if self.end_us <= self.start_us:
            raise ValueError("affected range end must be later than start")
        return self


class RenderGraphV2(RenderModel):
    schema_version: Literal["2.0"] = "2.0"
    graph_id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    timeline_revision: int = Field(ge=1)
    timeline_hash: str = Field(default="0" * 64, pattern=r"^[0-9a-f]{64}$")
    compiler_version: str = Field(default="rendergraph-v2", min_length=1, max_length=80)
    duration_us: int = Field(ge=0)
    canvas: GraphCanvas
    nodes: list[RenderNodeV2] = Field(default_factory=list)
    transitions: list[TransitionEdge] = Field(default_factory=list)
    assets: list[ResolvedAsset] = Field(default_factory=list)
    audio: AudioMixPlan = Field(default_factory=AudioMixPlan)
    subtitles: SubtitleRenderPlan = Field(default_factory=SubtitleRenderPlan)
    source_revisions: dict[str, str] = Field(default_factory=dict)
    affected_ranges: list[AffectedRange] = Field(default_factory=list)
    graph_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_contract_aliases(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "content_hash" in data and "graph_hash" not in data:
            data["graph_hash"] = data.pop("content_hash")
        if "audio_mix" in data and "audio" not in data:
            data["audio"] = data.pop("audio_mix")
        if "subtitle_plan" in data and "subtitles" not in data:
            data["subtitles"] = data.pop("subtitle_plan")
        return data

    @property
    def content_hash(self) -> str:
        return self.graph_hash

    @property
    def audio_mix(self) -> AudioMixPlan:
        return self.audio

    @property
    def subtitle_plan(self) -> SubtitleRenderPlan:
        return self.subtitles

    @model_validator(mode="after")
    def validate_graph(self) -> RenderGraphV2:
        if self.duration_us and any(node.end_us > self.duration_us for node in self.nodes):
            raise ValueError("render node exceeds graph duration")
        node_ids = {node.id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("render node ids must be unique")
        for edge in self.transitions:
            if edge.from_node_id not in node_ids or edge.to_node_id not in node_ids:
                raise ValueError("transition references unknown render node")
            if edge.end_us > self.duration_us:
                raise ValueError("transition exceeds graph duration")
        return self
