from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue

JobStatusValue = Literal[
    "queued",
    "running",
    "retry_wait",
    "cancelling",
    "succeeded",
    "failed",
    "cancelled",
]


class FrozenDto(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ArtifactInputDto(FrozenDto):
    artifact_id: UUID
    kind: str
    path: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SubmitJobDto(FrozenDto):
    schema_version: Literal["1.0"] = "1.0"
    job_id: UUID
    project_id: UUID
    job_type: str
    requested_by: str
    priority: int = Field(default=50, ge=0, le=100)
    idempotency_key: str
    inputs: tuple[ArtifactInputDto, ...] = ()
    parameters: dict[str, JsonValue]
    created_at: AwareDatetime


class SubmitJobResultDto(FrozenDto):
    job_id: UUID
    status: JobStatusValue
    created: bool


class ErrorDto(FrozenDto):
    category: str
    code: str
    message: str
    retryable: bool
    details: dict[str, JsonValue] = Field(default_factory=dict)


class JobStatusDto(FrozenDto):
    schema_version: Literal["1.0"]
    job_id: UUID
    project_id: UUID
    job_type: str
    status: JobStatusValue
    attempt_count: int = Field(ge=0)
    progress: int = Field(ge=0, le=100)
    next_attempt_at: AwareDatetime | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime
    error: ErrorDto | None = None


class ArtifactDto(FrozenDto):
    artifact_id: UUID
    job_id: UUID
    project_id: UUID
    logical_name: str
    kind: str
    version: int = Field(ge=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verified_at: AwareDatetime
    is_current: bool


class ActionRequestDto(FrozenDto):
    schema_version: Literal["1.0"] = "1.0"
    action: Literal["cancel", "retry"]
    requested_by: str
    requested_at: AwareDatetime
    reason: str | None = None
