from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from workbench.domain.enums import AttemptStatus, LeaseStatus, WorkerStatus


class JobInputSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: str = Field(min_length=1)
    fingerprint: str = Field(min_length=64, max_length=128)
    schema_version: str = Field(min_length=1, max_length=40)
    payload: dict[str, Any] = Field(default_factory=dict)


class JobAttemptRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    job_id: UUID
    generation: int = Field(ge=1)
    status: AttemptStatus
    worker_id: str | None = Field(default=None, min_length=1, max_length=120)
    runtime_fingerprint: str | None = Field(default=None, min_length=1, max_length=128)
    started_at: datetime
    heartbeat_at: datetime | None = None
    finished_at: datetime | None = None
    exit_code: int | None = None
    error_code: str | None = Field(default=None, max_length=96)
    checkpoint_sequence: int | None = Field(default=None, ge=1)
    revision: int = Field(default=1, ge=1)


class JobCheckpointRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    attempt_id: UUID
    sequence: int = Field(ge=1)
    checkpoint: dict[str, Any]
    checkpoint_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime


class ArtifactPublicationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    publication_key: str = Field(min_length=1, max_length=128)
    job_id: UUID
    attempt_id: UUID
    state: Literal["reserved", "published", "corrupted"]
    manifest: dict[str, Any]
    manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    published_at: datetime | None = None
    revision: int = Field(default=1, ge=1)


class ResourceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpu_cores: int = Field(default=1, ge=0, le=256)
    memory_mb: int = Field(default=512, ge=0, le=1_048_576)
    gpu_slots: int = Field(default=0, ge=0, le=16)
    disk_mb: int = Field(default=512, ge=0, le=10_485_760)


class ResourceLeaseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    job_id: UUID
    attempt_id: UUID
    worker_id: str = Field(min_length=1, max_length=120)
    generation: int = Field(ge=1)
    request: ResourceRequest
    status: LeaseStatus
    heartbeat_at: datetime
    expires_at: datetime
    revision: int = Field(default=1, ge=1)


class WorkerCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_types: list[str] = Field(min_length=1)
    encoders: list[str] = Field(default_factory=list)
    decoders: list[str] = Field(default_factory=list)
    hardware_acceleration: list[str] = Field(default_factory=list)
    max_concurrency: int = Field(default=1, ge=1, le=256)


class WorkerRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120)
    status: WorkerStatus
    runtime_fingerprint: str = Field(min_length=1, max_length=128)
    capabilities: WorkerCapability
    heartbeat_at: datetime
    revision: int = Field(default=1, ge=1)
