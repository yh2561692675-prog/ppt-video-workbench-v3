from __future__ import annotations

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workbench.audio.models import TranscriptWord
from workbench.subtitles.models import SubtitlePageRange, SubtitleTimeline


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SubtitlePageInput(SubtitlePageRange):
    narration_revision_id: UUID
    audio_narration_revision_id: UUID
    narration_text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_revision(self) -> Self:
        if self.narration_revision_id != self.audio_narration_revision_id:
            raise ValueError("subtitle page audio targets a stale narration revision")
        return self


class SubtitleBuildParameters(StrictPayload):
    route: Literal["local", "heygen"]
    duration_ms: int = Field(gt=0)
    pages: tuple[SubtitlePageInput, ...] = Field(min_length=1)
    words: tuple[TranscriptWord, ...] = ()

    @model_validator(mode="after")
    def validate_route(self) -> Self:
        page_ids = [item.page_id for item in self.pages]
        if len(page_ids) != len(set(page_ids)):
            raise ValueError("subtitle pages contain duplicate identities")
        if self.route == "local" and not self.words:
            raise ValueError("local subtitle build requires word timestamps")
        if self.route == "heygen" and self.words:
            raise ValueError("HeyGen subtitle build derives timestamps from confirmed narration")
        return self


class SubtitleArtifactDescriptor(StrictPayload):
    logical_name: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SubtitleTimelinePayload(StrictPayload):
    route: Literal["local", "heygen"]
    generated_at: datetime
    timeline: SubtitleTimeline
    srt: str = Field(min_length=1)
    narration_revisions: dict[UUID, UUID]
    artifacts: tuple[SubtitleArtifactDescriptor, SubtitleArtifactDescriptor]
