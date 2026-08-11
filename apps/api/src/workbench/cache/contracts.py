from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CacheDomain(StrEnum):
    VIDEO_ONLY = "video_only"
    AUDIO = "audio"
    SUBTITLE_SOFT = "subtitle_soft"
    SUBTITLE_BURN_IN = "subtitle_burn_in"
    TRANSITION = "transition"
    OVERLAY = "overlay"
    LAYOUT = "layout"
    FINAL = "final"


class CacheEntryState(StrEnum):
    READY = "ready"
    STALE = "stale"
    CORRUPTED = "corrupted"
    QUARANTINED = "quarantined"


class StaleReason(StrEnum):
    SOURCE_REVISION_CHANGED = "source_revision_changed"
    ASSET_REVISION_CHANGED = "asset_revision_changed"
    RUNTIME_INCOMPATIBLE = "runtime_incompatible"
    LICENSE_INVALID = "license_invalid"
    ARTIFACT_MISMATCH = "artifact_mismatch"
    LAYOUT_CHANGED = "layout_changed"


class CacheArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    relative_path: str = Field(min_length=1, max_length=500)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)


class CacheDependency(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    domain: CacheDomain
    node_key: str = Field(min_length=1, max_length=240)
    upstream_kind: str = Field(min_length=1, max_length=80)
    upstream_key: str = Field(min_length=1, max_length=500)
    upstream_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    start_us: int | None = Field(default=None, ge=0)
    end_us: int | None = Field(default=None, gt=0)
    artifact_refs: tuple[CacheArtifactRef, ...] = ()

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if (self.start_us is None) != (self.end_us is None):
            raise ValueError("cache dependency range requires both start_us and end_us")
        if self.start_us is not None and self.end_us is not None and self.end_us <= self.start_us:
            raise ValueError("cache dependency end must be later than start")
        return self

    @property
    def dependency_key(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class CacheInvalidationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_kind: str = Field(min_length=1, max_length=80)
    source_key: str = Field(min_length=1, max_length=500)
    previous_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    current_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    reason: StaleReason
    domains: tuple[CacheDomain, ...] = ()
    start_us: int | None = Field(default=None, ge=0)
    end_us: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if (self.start_us is None) != (self.end_us is None):
            raise ValueError("invalidation range requires both start_us and end_us")
        if self.start_us is not None and self.end_us is not None and self.end_us <= self.start_us:
            raise ValueError("invalidation end must be later than start")
        return self


def normalize_dependencies(
    dependencies: list[CacheDependency],
) -> tuple[CacheDependency, ...]:
    return tuple(
        sorted(
            dependencies,
            key=lambda item: (
                item.domain.value,
                item.node_key,
                item.upstream_kind,
                item.upstream_key,
                item.start_us if item.start_us is not None else -1,
                item.end_us if item.end_us is not None else -1,
                item.upstream_hash,
            ),
        )
    )
