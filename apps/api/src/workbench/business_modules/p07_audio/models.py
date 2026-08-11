from __future__ import annotations

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workbench.audio.models import Transcript
from workbench.domain.audio import AudioDifference, AudioImportRecord, AudioTimeline


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConfirmedNarration(StrictPayload):
    page_id: UUID
    page_order: int = Field(ge=1)
    revision_id: UUID
    confirmed_revision_id: UUID
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_confirmation(self) -> Self:
        if self.revision_id != self.confirmed_revision_id:
            raise ValueError("audio requires the current confirmed narration revision")
        return self


class AudioNormalizeParameters(StrictPayload):
    source_name: str = Field(min_length=1, max_length=255)
    existing_route: Literal["local", "none"] = "none"


class AudioTranscribeParameters(StrictPayload):
    device: Literal["cpu", "cuda"] = "cpu"
    model: str = Field(default="small", min_length=1, max_length=80)
    language: str = Field(default="zh", min_length=1, max_length=16)
    existing_route: Literal["local", "none"] = "local"


class AudioAlignParameters(StrictPayload):
    transcript: Transcript
    narrations: tuple[ConfirmedNarration, ...] = Field(min_length=1)
    audio_import: AudioImportRecord
    min_page_ms: int = Field(default=300, ge=1)
    existing_route: Literal["local", "none"] = "local"

    @model_validator(mode="after")
    def validate_pages(self) -> Self:
        page_ids = [item.page_id for item in self.narrations]
        orders = [item.page_order for item in self.narrations]
        if len(page_ids) != len(set(page_ids)) or orders != sorted(orders):
            raise ValueError("aligned narrations must have unique pages in ascending order")
        return self


class ExistingPageAudio(StrictPayload):
    page_id: UUID
    narration_revision_id: UUID
    cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    relative_path: str = Field(min_length=1)
    duration_ms: int = Field(gt=0)
    voice_id: str = Field(min_length=1)
    remote_request_id: str = Field(min_length=1)


class AudioSynthesizeParameters(StrictPayload):
    profile_id: UUID
    voice_id: str = Field(min_length=1, max_length=200)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    narrations: tuple[ConfirmedNarration, ...] = Field(min_length=1)
    existing_route: Literal["heygen", "none"] = "none"
    existing_page_audio: tuple[ExistingPageAudio, ...] = ()

    @model_validator(mode="after")
    def validate_pages(self) -> Self:
        narration_ids = [item.page_id for item in self.narrations]
        existing_ids = [item.page_id for item in self.existing_page_audio]
        if len(narration_ids) != len(set(narration_ids)):
            raise ValueError("synthesis narrations contain duplicate pages")
        if len(existing_ids) != len(set(existing_ids)):
            raise ValueError("existing page audio contains duplicate pages")
        if not set(existing_ids).issubset(narration_ids):
            raise ValueError("existing page audio references an unknown page")
        return self


class ArtifactDescriptor(StrictPayload):
    logical_name: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PageAudioResult(StrictPayload):
    id: UUID
    page_id: UUID
    source: Literal["local", "heygen"]
    relative_path: str = Field(min_length=1)
    duration_ms: int = Field(gt=0)
    cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    narration_revision_id: UUID
    voice_id: str | None = None
    remote_request_id: str | None = None
    cached: bool = False

    @model_validator(mode="after")
    def validate_remote_fields(self) -> Self:
        if self.source == "heygen" and (not self.voice_id or not self.remote_request_id):
            raise ValueError("HeyGen page audio requires voice and remote request identity")
        if self.source == "local" and (self.voice_id or self.remote_request_id):
            raise ValueError("local page audio cannot contain remote identity")
        return self


class RemoteRequestAudit(StrictPayload):
    page_id: UUID
    cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_id: str = Field(min_length=1)
    reused: bool = False


class AudioPipelinePayload(StrictPayload):
    operation: Literal["normalize", "transcribe", "align", "synthesize"]
    route: Literal["local", "heygen"]
    generated_at: datetime
    audio_import: AudioImportRecord | None = None
    transcript: Transcript | None = None
    differences: tuple[AudioDifference, ...] = ()
    timeline: AudioTimeline | None = None
    page_audio: tuple[PageAudioResult, ...] = ()
    remote_requests: tuple[RemoteRequestAudit, ...] = ()
    artifacts: tuple[ArtifactDescriptor, ...] = ()

    @model_validator(mode="after")
    def validate_operation(self) -> Self:
        if self.operation == "normalize" and self.audio_import is None:
            raise ValueError("normalize result requires audio_import")
        if self.operation == "transcribe" and self.transcript is None:
            raise ValueError("transcribe result requires transcript")
        if self.operation == "align" and (self.timeline is None or not self.page_audio):
            raise ValueError("align result requires timeline and page audio")
        if self.operation == "synthesize" and (
            self.route != "heygen" or not self.page_audio or not self.remote_requests
        ):
            raise ValueError("synthesize result requires HeyGen page audio and request audit")
        return self
