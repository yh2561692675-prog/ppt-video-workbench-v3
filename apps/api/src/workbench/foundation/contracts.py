from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_SHA256 = r"^[0-9a-f]{64}$"
_GIT_SHA = r"^[0-9a-f]{40}$"


def _logical_path(value: str) -> str:
    """Accept a project-relative/logical path and reject escape attempts."""

    normalized = value.replace("\\", "/")
    if (
        not normalized
        or normalized.startswith("/")
        or ":" in normalized[:3]
        or any(part in {"", ".", ".."} for part in normalized.split("/"))
    ):
        raise ValueError("path must be non-empty, relative, and normalized")
    return normalized


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RepositoryRefV1(_StrictModel):
    path: str = Field(min_length=1)
    branch: str = Field(min_length=1)
    head: str = Field(pattern=_GIT_SHA)
    status_manifest_sha256: str = Field(pattern=_SHA256)


class WindowStopPointV1(_StrictModel):
    schema_version: Literal["1.0"]
    window_id: str = Field(min_length=1, max_length=160)
    task_name: str = Field(min_length=1, max_length=240)
    mode: Literal["writer", "read_only", "idle"]
    repository: RepositoryRefV1
    owned_paths: list[str] = Field(default_factory=list)
    shared_paths_touched: list[str] = Field(default_factory=list)
    completed: list[str] = Field(default_factory=list)
    remaining: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    will_write_again: bool
    safe_resume: str = Field(min_length=1, max_length=4000)

    _owned_paths = field_validator("owned_paths", "shared_paths_touched", "evidence_refs")(
        lambda values: [_logical_path(value) for value in values]
    )


class OwnershipEntryV1(_StrictModel):
    path: str
    owner_window_id: str = Field(min_length=1)
    category: Literal[
        "source",
        "test",
        "contract",
        "doc",
        "generated",
        "cache",
        "backup",
        "evidence",
        "user_data",
    ]
    authority: bool

    _path = field_validator("path")(_logical_path)


class OwnershipMapV1(_StrictModel):
    schema_version: Literal["1.0"]
    generated_at: datetime
    entries: list[OwnershipEntryV1] = Field(default_factory=list)
    unknown_paths: list[str] = Field(default_factory=list)
    semantic_conflicts: list[str] = Field(default_factory=list)
    source_status_manifest_sha256: str = Field(pattern=_SHA256)

    _unknown_paths = field_validator("unknown_paths")(
        lambda values: [_logical_path(value) for value in values]
    )
    _conflicts = field_validator("semantic_conflicts")(
        lambda values: [_logical_path(value) for value in values]
    )


class BoundaryRecordV1(_StrictModel):
    boundary_id: Literal["source", "installed", "workspace_data", "video"]
    logical_root: str = Field(min_length=1)
    exists: bool
    writable: bool
    containment_verified: bool


class FoundationFreezeManifestV1(_StrictModel):
    schema_version: Literal["1.0"]
    foundation_id: str = Field(pattern=r"^foundation-[0-9]{8}-[0-9]{6}-[0-9a-f]{7,40}$")
    created_at: datetime
    repository: RepositoryRefV1
    checkpoint_ref: str = Field(min_length=1)
    snapshot_sha256: str = Field(pattern=_SHA256)
    stop_point_ids: list[str] = Field(default_factory=list)
    ownership_map_sha256: str = Field(pattern=_SHA256)
    conflict_resolution_sha256: str = Field(pattern=_SHA256)
    boundaries: list[BoundaryRecordV1] = Field(min_length=4)
    includes: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)
    dependency_lock_sha256: str = Field(pattern=_SHA256)
    gate_evidence_refs: list[str] = Field(default_factory=list)
    release_level: Literal[
        "inventory",
        "waiting_for_stop_points",
        "candidate",
        "foundation_ready",
        "render_ready",
        "release_ready",
        "rejected",
    ]

    _includes = field_validator("includes", "excludes", "gate_evidence_refs")(
        lambda values: [_logical_path(value) for value in values]
    )


class EvidenceCountsV1(_StrictModel):
    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    warnings: int = Field(default=0, ge=0)


class GateEvidenceV1(_StrictModel):
    schema_version: Literal["1.0"]
    gate_id: str = Field(pattern=r"^G[0-7](?:-[A-Z0-9-]+)?$")
    command_id: str = Field(min_length=1)
    foundation_id: str = Field(min_length=1)
    snapshot_sha256: str = Field(pattern=_SHA256)
    status: Literal["passed", "failed", "cancelled", "invalid"]
    started_at: datetime
    finished_at: datetime
    exit_code: int | None = None
    tool_versions: dict[str, str] = Field(default_factory=dict)
    counts: EvidenceCountsV1 = Field(default_factory=EvidenceCountsV1)
    log_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    invalid_reason: str | None = Field(default=None, max_length=2000)
    approved_by: str | None = Field(default=None, max_length=240)
    approved_at: datetime | None = None

    _log_refs = field_validator("log_refs", "artifact_refs")(
        lambda values: [_logical_path(value) for value in values]
    )
