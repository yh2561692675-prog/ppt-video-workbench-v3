from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SubtitleModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SubtitleBuildError(ValueError):
    """Raised when a subtitle timeline cannot be proven from word timestamps."""


class SubtitlePageRange(SubtitleModel):
    page_id: UUID
    page_order: int = Field(ge=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> SubtitlePageRange:
        if self.end_ms <= self.start_ms:
            raise ValueError("字幕页面结束时间必须晚于开始时间")
        return self


class SubtitleCue(SubtitleModel):
    id: UUID
    page_id: UUID
    page_order: int = Field(ge=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    text: str = Field(min_length=1)
    source_word_indexes: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_range(self) -> SubtitleCue:
        if self.end_ms <= self.start_ms:
            raise ValueError("字幕结束时间必须晚于开始时间")
        return self


class SubtitleTimeline(SubtitleModel):
    version: int = Field(default=1, ge=1)
    duration_ms: int = Field(ge=0)
    cues: list[SubtitleCue] = Field(default_factory=list)
