from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContinuityModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TransitionKind(StrEnum):
    CUT = "cut"
    DISSOLVE = "dissolve"
    WIPE = "wipe"
    SLIDE = "slide"
    MATCH = "match"


class AudioCutMode(StrEnum):
    CUT = "cut"
    J_CUT = "j_cut"
    L_CUT = "l_cut"


class TransitionSpec(ContinuityModel):
    id: UUID = Field(default_factory=uuid4)
    from_page_id: UUID
    to_page_id: UUID
    kind: TransitionKind = TransitionKind.CUT
    duration_ms: int = Field(default=0, ge=0, le=10_000)
    audio_mode: AudioCutMode = AudioCutMode.CUT
    audio_offset_ms: int = Field(default=0, ge=-10_000, le=10_000)
    easing: Literal["linear", "ease_in", "ease_out", "ease_in_out"] = "ease_in_out"
    enabled: bool = True
    chapter_boundary: bool = False
    parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_transition(self) -> TransitionSpec:
        if self.from_page_id == self.to_page_id:
            raise ValueError("transition pages must be different")
        if self.kind == TransitionKind.CUT and self.duration_ms != 0:
            raise ValueError("cut transition duration must be zero")
        if self.audio_mode == AudioCutMode.CUT and self.audio_offset_ms != 0:
            raise ValueError("cut audio mode cannot have an offset")
        return self


class OverlayPlacement(ContinuityModel):
    id: UUID = Field(default_factory=uuid4)
    source_ref: str = Field(min_length=1, max_length=500)
    kind: Literal["image", "video", "logo", "sticker", "text"]
    start_ms: int = Field(ge=0)
    duration_ms: int = Field(gt=0)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)
    opacity: float = Field(default=1, ge=0, le=1)
    crop: Literal["contain", "cover", "fill"] = "contain"
    mask: Literal["none", "circle", "rounded"] = "none"
    enter_ms: int = Field(default=0, ge=0, le=5_000)
    exit_ms: int = Field(default=0, ge=0, le=5_000)
    license_asset_id: UUID | None = None
    z_index: int = Field(default=10, ge=0, le=999)

    @model_validator(mode="after")
    def validate_bounds(self) -> OverlayPlacement:
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("overlay placement exceeds canvas bounds")
        if self.enter_ms + self.exit_ms > self.duration_ms:
            raise ValueError("overlay entrance and exit exceed duration")
        return self


class ChapterMarker(ContinuityModel):
    id: UUID = Field(default_factory=uuid4)
    title: str = Field(min_length=1, max_length=160)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    page_ids: list[UUID] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_range(self) -> ChapterMarker:
        if self.end_ms <= self.start_ms:
            raise ValueError("chapter end must be later than start")
        return self


class ContinuityPlan(ContinuityModel):
    version: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    project_id: UUID
    duration_ms: int = Field(ge=0)
    transitions: list[TransitionSpec] = Field(default_factory=list)
    overlays: list[OverlayPlacement] = Field(default_factory=list)
    chapters: list[ChapterMarker] = Field(default_factory=list)
    content_hash: str = Field(default="", pattern=r"^[0-9a-f]{64}$|^$")


CommandKind = Literal[
    "upsert_transition",
    "remove_transition",
    "upsert_overlay",
    "remove_overlay",
    "upsert_chapter",
    "remove_chapter",
]


class ContinuityPlanCommand(ContinuityModel):
    command_id: UUID = Field(default_factory=uuid4)
    expected_revision: int = Field(ge=1)
    kind: CommandKind
    payload: dict[str, Any] = Field(default_factory=dict)
