from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TranscriptContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PresenterTranscriptWord(TranscriptContract):
    id: str = Field(min_length=1)
    text: str
    normalized_text: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)


class PresenterTranscriptSentence(TranscriptContract):
    id: str = Field(min_length=1)
    text: str
    normalized_text: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    word_ids: list[str] = Field(default_factory=list)
    review_reasons: list[str] = Field(default_factory=list)


class TranscriptRevision(TranscriptContract):
    id: UUID
    source_hash: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    audio_hash: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    duration_ms: int = Field(gt=0)
    detected_language: str
    model_version: str
    glossary_version: str
    cache_key: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    content_hash: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    words: list[PresenterTranscriptWord] = Field(default_factory=list)
    sentences: list[PresenterTranscriptSentence] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_timestamps(self) -> TranscriptRevision:
        previous_end = 0
        for word in self.words:
            if word.end_ms <= word.start_ms or word.start_ms < previous_end:
                raise ValueError("presenter word timestamps must be monotonic")
            if word.end_ms > self.duration_ms:
                raise ValueError("presenter word timestamp exceeds media duration")
            previous_end = word.end_ms
        for sentence in self.sentences:
            if sentence.end_ms <= sentence.start_ms or sentence.end_ms > self.duration_ms:
                raise ValueError("presenter sentence timestamp is invalid")
        return self
