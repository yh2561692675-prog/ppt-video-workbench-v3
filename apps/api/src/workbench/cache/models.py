from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from workbench.cache.contracts import CacheDependency, CacheDomain, CacheEntryState


class CacheEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    project_id: UUID
    artifact_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    relative_path: str = Field(min_length=1, max_length=500)
    size_bytes: int = Field(ge=0)
    dependencies: list[str] = Field(default_factory=list)
    rebuildable: bool = True
    protected: bool = False
    lease_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_accessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CacheGcCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cache_key: str
    relative_path: str
    size_bytes: int = Field(ge=0)
    reason: str


class CacheGcResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool
    bytes_before: int = Field(ge=0)
    bytes_reclaimed: int = Field(ge=0)
    candidates: list[CacheGcCandidate]


class PersistentCacheEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    project_id: UUID
    domain: CacheDomain
    node_key: str = Field(min_length=1, max_length=240)
    state: CacheEntryState = CacheEntryState.READY
    artifact_manifest: dict[str, object]
    artifact_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    relative_path: str = Field(min_length=1, max_length=500)
    artifact_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    runtime_fingerprint: str = Field(min_length=1, max_length=128)
    license_status: str = Field(default="unknown", min_length=1, max_length=24)
    dependencies: tuple[CacheDependency, ...] = ()
    rebuildable: bool = True
    protected: bool = False
    lease_count: int = Field(default=0, ge=0)
    stale_reason: str | None = Field(default=None, max_length=80)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_accessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    revision: int = Field(default=1, ge=1)


class CacheLookupResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hit: bool
    reason: str
    entry: PersistentCacheEntry | None = None
