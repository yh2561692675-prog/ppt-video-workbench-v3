from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AudioContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AudioImportRecord(AudioContractModel):
    id: UUID
    original_relative_path: str
    normalized_relative_path: str
    duration_ms: int = Field(ge=0)
    sample_rate: int = Field(ge=1)
    channels: int = Field(ge=1)
    sha256: str = Field(min_length=64, max_length=64)
    peak_dbfs: float
    silence_ratio: float = Field(ge=0, le=1)
    silence_intervals_ms: list[tuple[int, int]] = Field(default_factory=list)
    needs_confirmation: bool = False
    imported_at: datetime


class AudioDifference(AudioContractModel):
    id: UUID
    page_id: UUID
    kind: Literal["omission", "addition", "misread", "uncertain"]
    expected: str
    actual: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    status: Literal["pending", "resolved"] = "pending"
    resolution: Literal["accept_recording", "change_narration", "reimport"] | None = None
    resolved_at: datetime | None = None


class AudioTimelineBoundary(AudioContractModel):
    id: UUID
    time_ms: int = Field(ge=0)


class AudioTimelineSegment(AudioContractModel):
    page_id: UUID
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)


class AudioTimeline(AudioContractModel):
    id: UUID
    version: int = Field(default=1, ge=1)
    duration_ms: int = Field(ge=0)
    min_page_ms: int = Field(default=300, ge=1)
    boundaries: list[AudioTimelineBoundary] = Field(default_factory=list)
    segments: list[AudioTimelineSegment] = Field(default_factory=list)


class AudioAsset(AudioContractModel):
    page_id: UUID
    relative_path: str
    duration_ms: int = Field(ge=0)
    source: Literal["heygen"] = "heygen"
    cache_key: str
    voice_id: str
    request_id: str
    cached: bool = False


class SubtitleArtifact(AudioContractModel):
    timeline_relative_path: str
    srt_relative_path: str
    timeline_sha256: str = Field(min_length=64, max_length=64)
    srt_sha256: str = Field(min_length=64, max_length=64)
