"""Versioned candidate contracts for AI content assistance."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator

from workbench.contracts.p2_platform import _ContractModel, _validate_utc

AssistKind = Literal["polish", "segment", "translate"]


class ContentAssistRequestV1(_ContractModel):
    schema_version: Literal[1] = 1
    request_id: UUID = Field(default_factory=uuid4)
    kind: AssistKind
    source_text: str = Field(min_length=1, max_length=200_000)
    source_language: str = Field(default="zh-CN", min_length=2, max_length=32)
    target_language: str | None = Field(default=None, min_length=2, max_length=32)
    max_segment_chars: int = Field(default=60, ge=10, le=500)
    style: Literal["neutral", "spoken", "concise"] = "neutral"
    source_revision_id: UUID | None = None

    @field_validator("source_text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        clean = value.strip()
        if not clean:
            raise ValueError("source_text must not be blank")
        return clean


class ContentAssistCandidateV1(_ContractModel):
    schema_version: Literal[1] = 1
    candidate_id: UUID = Field(default_factory=uuid4)
    request_id: UUID
    kind: AssistKind
    status: Literal["candidate", "accepted", "rejected", "needs_provider"] = "candidate"
    source_text: str = Field(min_length=1)
    candidate_text: str = Field(min_length=1)
    source_language: str
    target_language: str | None = None
    segments: list[str] = Field(default_factory=list, max_length=10_000)
    provider_id: str | None = None
    warnings: list[str] = Field(default_factory=list, max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    accepted_at: datetime | None = None

    @field_validator("created_at", "accepted_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _validate_utc(value)
