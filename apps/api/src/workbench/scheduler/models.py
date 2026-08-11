from __future__ import annotations

from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class SchedulerModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BatchStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BatchItemStatus(StrEnum):
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BatchResourceLimits(SchedulerModel):
    max_parallel: int = Field(default=1, ge=1, le=32)
    cpu_cores: int = Field(default=4, ge=1, le=256)
    memory_mb: int = Field(default=8_192, ge=512, le=1_048_576)
    gpu_slots: int = Field(default=0, ge=0, le=16)
    per_job_memory_mb: int = Field(default=4_096, ge=256, le=1_048_576)


class BatchItem(SchedulerModel):
    item_id: UUID = Field(default_factory=uuid4)
    preset_id: str = Field(min_length=1, max_length=64)
    page_id: UUID | None = None
    priority: int = Field(default=50, ge=0, le=100)
    dependencies: list[UUID] = Field(default_factory=list)
    resource_cpu: int = Field(default=1, ge=1, le=256)
    resource_memory_mb: int = Field(default=2_048, ge=256, le=1_048_576)
    resource_gpu: int = Field(default=0, ge=0, le=16)
    status: BatchItemStatus = BatchItemStatus.QUEUED
    job_id: UUID | None = None
    attempts: int = Field(default=0, ge=0)
    error: str | None = None


class BatchProduction(SchedulerModel):
    version: int = Field(default=1, ge=1)
    revision: int = Field(default=1, ge=1)
    batch_id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    created_at: str
    status: BatchStatus = BatchStatus.QUEUED
    night_queue: bool = False
    resource_limits: BatchResourceLimits
    items: list[BatchItem] = Field(min_length=1)
    content_hash: str = Field(default="", pattern=r"^[0-9a-f]{64}$|^$")


class BatchCreateRequest(SchedulerModel):
    preset_ids: list[str] = Field(min_length=1, max_length=32)
    page_ids: list[UUID] = Field(default_factory=list, max_length=1_000)
    priority: int = Field(default=50, ge=0, le=100)
    night_queue: bool = False
    resource_limits: BatchResourceLimits = Field(default_factory=BatchResourceLimits)


class BatchDispatchRequest(SchedulerModel):
    allow_night: bool = False
    available_cpu: int | None = Field(default=None, ge=1)
    available_memory_mb: int | None = Field(default=None, ge=512)
    available_gpu: int | None = Field(default=None, ge=0)


class BatchDispatchResult(SchedulerModel):
    batch: BatchProduction
    dispatched_item_ids: list[UUID] = Field(default_factory=list)


class BatchRerunRequest(SchedulerModel):
    item_ids: list[UUID] = Field(min_length=1, max_length=1_000)
