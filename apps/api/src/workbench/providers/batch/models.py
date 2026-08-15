"""Versioned state for resumable remote provider batches."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from workbench.contracts.p2_platform import _ContractModel, _validate_utc

BatchItemStatus = Literal["pending", "running", "succeeded", "failed", "unknown_billed"]
BatchStatus = Literal["queued", "running", "paused", "succeeded", "failed", "unknown_billed"]


class ProviderBatchItemV1(_ContractModel):
    schema_version: Literal[1] = 1
    item_id: UUID = Field(default_factory=uuid4)
    page_id: UUID
    status: BatchItemStatus = "pending"
    attempt_count: int = Field(default=0, ge=0, le=20)
    remote_request_ids: list[str] = Field(default_factory=list, max_length=32)
    output_ref: str | None = Field(default=None, max_length=1024)
    error_code: str | None = Field(default=None, max_length=100)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    _updated_at = field_validator("updated_at")(_validate_utc)


class ProviderBatchJobV1(_ContractModel):
    schema_version: Literal[1] = 1
    job_id: UUID = Field(default_factory=uuid4)
    provider_id: str = Field(min_length=1, max_length=128)
    operation_kind: Literal["tts", "asr", "avatar", "renderer"]
    project_id: UUID
    revision_id: UUID
    item_ids: list[UUID] = Field(min_length=1, max_length=10_000)
    status: BatchStatus = "queued"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_error_code: str | None = Field(default=None, max_length=100)
    unknown_billed_item_ids: list[UUID] = Field(default_factory=list, max_length=10_000)

    _timestamps = field_validator("created_at", "updated_at")(_validate_utc)

    @model_validator(mode="after")
    def validate_unknown_state(self) -> ProviderBatchJobV1:
        if self.unknown_billed_item_ids and self.status != "unknown_billed":
            raise ValueError("jobs with unknown billed items must be unknown_billed")
        return self
