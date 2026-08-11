from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PresenterContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PresentationMode(StrEnum):
    AI_NARRATION = "ai_narration"
    HUMAN_PRESENTER = "human_presenter"


class PresenterSource(PresenterContract):
    id: UUID
    relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    duration_ms: int = Field(gt=0)
    media_type: Literal["video/mp4", "video/quicktime"] = "video/mp4"
    probe_snapshot: dict[str, Any] = Field(default_factory=dict)
    imported_at: datetime | None = None


class SlideAnchor(PresenterContract):
    page_id: UUID
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    sentence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    status: Literal["auto", "review", "blocked", "confirmed"]
    manual_lock: bool = False
    source_revision: str | None = None

    @model_validator(mode="after")
    def validate_anchor(self) -> SlideAnchor:
        if self.end_ms <= self.start_ms:
            raise ValueError("anchor end must be after start")
        if self.manual_lock and not self.source_revision:
            raise ValueError("manual lock requires source_revision")
        return self


class PresenterSegment(PresenterContract):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    layout: Literal[
        "top_left",
        "top_right",
        "bottom_left",
        "bottom_right",
        "center",
        "split",
        "hidden",
    ]
    width_ratio: float = Field(ge=0, le=1)
    manual_lock: bool = False
    source_revision: str | None = None

    @model_validator(mode="after")
    def validate_segment(self) -> PresenterSegment:
        if self.end_ms <= self.start_ms:
            raise ValueError("segment end must be after start")
        if self.layout != "hidden" and self.width_ratio <= 0:
            raise ValueError("visible presenter segment requires positive width_ratio")
        if self.manual_lock and not self.source_revision:
            raise ValueError("manual lock requires source_revision")
        return self


class PresenterTimeRange(PresenterContract):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    reason: str = "unassigned"

    @model_validator(mode="after")
    def validate_range(self) -> PresenterTimeRange:
        if self.end_ms <= self.start_ms:
            raise ValueError("time range end must be after start")
        return self


class PresenterTimelineV1(PresenterContract):
    schema_version: Literal["1.0"] = "1.0"
    revision: int = Field(default=1, ge=1)
    source_id: UUID
    source_version: str = Field(min_length=1)
    duration_ms: int = Field(gt=0)
    anchors: list[SlideAnchor] = Field(default_factory=list)
    segments: list[PresenterSegment] = Field(default_factory=list)
    unassigned_ranges: list[PresenterTimeRange] = Field(default_factory=list)
    timeline_hash: str | None = None
    generated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_timeline(self) -> PresenterTimelineV1:
        self._validate_ordered_ranges(self.anchors, "anchor")
        self._validate_ordered_ranges(self.segments, "segment")
        self._validate_ordered_ranges(self.unassigned_ranges, "unassigned range")
        page_ids = [anchor.page_id for anchor in self.anchors]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("presenter anchors contain duplicate page ids")
        return self

    def _validate_ordered_ranges(
        self,
        ranges: list[SlideAnchor] | list[PresenterSegment] | list[PresenterTimeRange],
        label: str,
    ) -> None:
        previous_end = 0
        for item in ranges:
            if item.end_ms > self.duration_ms:
                raise ValueError(f"{label} exceeds presenter duration")
            if item.start_ms < previous_end:
                raise ValueError(f"{label} overlap is not allowed")
            previous_end = item.end_ms
