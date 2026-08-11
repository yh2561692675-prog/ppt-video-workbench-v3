from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SubtitleWorkbenchModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SubtitleRenderMode(StrEnum):
    SOFT = "soft"
    BURN_IN = "burn_in"
    BOTH = "both"
    NONE = "none"


class SubtitlePosition(StrEnum):
    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


class SubtitleStyleTemplate(SubtitleWorkbenchModel):
    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=80)
    font_family: str = Field(default="Noto Sans CJK SC", min_length=1, max_length=120)
    font_size: int = Field(default=48, ge=8, le=240)
    color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    outline_color: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    outline_width: int = Field(default=2, ge=0, le=32)
    background_color: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    background_opacity: float = Field(default=0.55, ge=0, le=1)
    position: SubtitlePosition = SubtitlePosition.BOTTOM
    animation: Literal["none", "fade", "word_highlight"] = "none"
    highlight_color: str = Field(default="#FFD54F", pattern=r"^#[0-9A-Fa-f]{6}$")


class SubtitleWordTiming(SubtitleWorkbenchModel):
    text: str = Field(min_length=1, max_length=200)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    highlighted: bool = False

    @model_validator(mode="after")
    def validate_range(self) -> SubtitleWordTiming:
        if self.end_ms <= self.start_ms:
            raise ValueError("word timing end must be later than start")
        return self


class SubtitleCueV2(SubtitleWorkbenchModel):
    id: UUID = Field(default_factory=uuid4)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=2000)
    translation: str | None = Field(default=None, max_length=2000)
    words: list[SubtitleWordTiming] = Field(default_factory=list)
    style_template_id: UUID | None = None
    style_override: SubtitleStyleTemplate | None = None
    line_breaks: list[int] = Field(default_factory=list)
    source_word_indexes: list[int] = Field(default_factory=list)
    locked: bool = False

    @model_validator(mode="after")
    def validate_range(self) -> SubtitleCueV2:
        if self.end_ms <= self.start_ms:
            raise ValueError("subtitle cue end must be later than start")
        if any(index < 1 for index in self.line_breaks):
            raise ValueError("line breaks must be positive character indexes")
        return self


class SubtitleLanguageTrack(SubtitleWorkbenchModel):
    id: UUID = Field(default_factory=uuid4)
    language: str = Field(min_length=2, max_length=16)
    label: str = Field(min_length=1, max_length=80)
    primary: bool = False
    visible: bool = True
    cues: list[SubtitleCueV2] = Field(default_factory=list)


class SubtitleWorkbenchDocument(SubtitleWorkbenchModel):
    version: int = Field(default=2, ge=2)
    revision: int = Field(default=1, ge=1)
    duration_ms: int = Field(ge=0)
    render_mode: SubtitleRenderMode = SubtitleRenderMode.SOFT
    default_style: SubtitleStyleTemplate
    templates: list[SubtitleStyleTemplate] = Field(default_factory=list)
    tracks: list[SubtitleLanguageTrack] = Field(min_length=1)
    updated_at: str
    content_hash: str = Field(default="", pattern=r"^[0-9a-f]{64}$|^$")

    @model_validator(mode="after")
    def validate_tracks(self) -> SubtitleWorkbenchDocument:
        if not any(track.primary for track in self.tracks):
            raise ValueError("subtitle document requires one primary track")
        languages = [track.language for track in self.tracks]
        if len(set(languages)) != len(languages):
            raise ValueError("subtitle track languages must be unique")
        for track in self.tracks:
            for cue in track.cues:
                if cue.end_ms > self.duration_ms:
                    raise ValueError("subtitle cue exceeds document duration")
        return self


CommandKind = Literal[
    "update_cue",
    "split_cue",
    "merge_cues",
    "retime_cue",
    "set_style",
    "set_translation",
    "set_render_mode",
    "toggle_track",
    "upsert_template",
    "set_word_highlight",
]


class SubtitleWorkbenchCommand(SubtitleWorkbenchModel):
    command_id: UUID = Field(default_factory=uuid4)
    expected_revision: int = Field(ge=1)
    kind: CommandKind
    payload: dict[str, Any] = Field(default_factory=dict)


class SubtitleTranslationRequest(SubtitleWorkbenchModel):
    language: str = Field(min_length=2, max_length=16)
    label: str = Field(min_length=1, max_length=80)
    translations: dict[str, str] = Field(default_factory=dict)


class SubtitleTranslationResult(SubtitleWorkbenchModel):
    document: SubtitleWorkbenchDocument
    translated_cue_count: int = Field(ge=0)
