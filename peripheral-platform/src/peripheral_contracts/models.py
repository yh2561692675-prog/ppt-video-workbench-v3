from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)

from peripheral_contracts.enums import ActionType, ErrorCategory, JobStatus
from peripheral_contracts.versioning import require_supported_major


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VersionedModel(StrictModel):
    schema_version: Literal["1.0"]

    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> Self:
        if isinstance(obj, Mapping):
            require_supported_major(obj.get("schema_version"))
        return super().model_validate(obj, **kwargs)


class ArtifactRef(StrictModel):
    artifact_id: UUID
    kind: str = Field(min_length=1, max_length=64)
    path: str = Field(min_length=1, max_length=1024)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class JobEnvelope(VersionedModel):
    job_id: UUID
    project_id: UUID
    job_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,63}$")
    requested_by: str = Field(min_length=1, max_length=64)
    priority: int = Field(default=50, ge=0, le=100)
    idempotency_key: str = Field(min_length=16, max_length=128)
    inputs: tuple[ArtifactRef, ...] = ()
    parameters: dict[str, JsonValue]
    created_at: AwareDatetime


class EventEnvelope(VersionedModel):
    event_id: UUID
    job_id: UUID
    project_id: UUID
    source: str = Field(min_length=1, max_length=64)
    event_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,63}$")
    severity: Literal["debug", "info", "warning", "error"]
    occurred_at: AwareDatetime
    data: dict[str, JsonValue]


class OutputArtifact(StrictModel):
    logical_name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    kind: str = Field(min_length=1, max_length=64)
    staged_path: str = Field(min_length=1, max_length=1024)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ErrorDetail(StrictModel):
    category: ErrorCategory
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,63}$")
    message: str = Field(min_length=1, max_length=512)
    retryable: bool
    details: dict[str, JsonValue] = Field(default_factory=dict)


class JobResult(VersionedModel):
    job_id: UUID
    outcome: Literal["succeeded", "failed"]
    outputs: tuple[OutputArtifact, ...] = ()
    error: ErrorDetail | None = None

    @model_validator(mode="after")
    def validate_outcome_details(self) -> Self:
        if self.outcome == "failed" and self.error is None:
            raise ValueError("failed result requires error")
        if self.outcome == "succeeded" and self.error is not None:
            raise ValueError("succeeded result cannot contain error")
        return self


class ArtifactManifest(VersionedModel):
    job_id: UUID
    artifacts: tuple[ArtifactRef, ...]
    created_at: AwareDatetime


class ModuleManifest(VersionedModel):
    module_name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    module_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    job_types: tuple[str, ...] = Field(min_length=1)
    max_runtime_seconds: int = Field(ge=1, le=86400)


class ActionRequest(VersionedModel):
    action: ActionType
    requested_by: str = Field(min_length=1, max_length=64)
    requested_at: AwareDatetime
    reason: str | None = Field(default=None, max_length=256)


class JobStatusResponse(VersionedModel):
    job_id: UUID
    project_id: UUID
    job_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,63}$")
    status: JobStatus
    attempt_count: int = Field(ge=0)
    progress: int = Field(ge=0, le=100)
    next_attempt_at: AwareDatetime | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    error: ErrorDetail | None = None
