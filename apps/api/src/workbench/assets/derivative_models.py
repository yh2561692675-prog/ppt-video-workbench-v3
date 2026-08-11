from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DerivativeOperation(StrEnum):
    CROP = "crop"
    TRANSCODE = "transcode"
    PROXY = "proxy"
    THUMBNAIL = "thumbnail"
    WAVEFORM = "waveform"
    REMOVE_BACKGROUND = "remove_background"


class DerivativeRequestV1(BaseModel):
    """Immutable, content-addressed input for one derived media artifact."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    parent_asset_id: UUID
    parent_revision: int = Field(ge=1)
    parent_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation: DerivativeOperation
    parameters: dict[str, Any] = Field(default_factory=dict)
    output_slot: str = Field(min_length=1, max_length=80)
    tool_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("output_slot")
    @classmethod
    def output_slot_must_not_be_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
            raise ValueError("output_slot must be a single relative identifier")
        return value

    @property
    def fingerprint(self) -> str:
        return derivative_fingerprint(self)


class DerivativeArtifactManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    object_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    relative_object_path: str = Field(min_length=1, max_length=500)
    size_bytes: int = Field(ge=0)
    mime_type: str = Field(min_length=1, max_length=120)
    parent_content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    tool_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    lineage: list[str] = Field(default_factory=list)

    @field_validator("relative_object_path")
    @classmethod
    def object_path_must_be_relative(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("object path must be relative")
        return value


def derivative_fingerprint(request: DerivativeRequestV1) -> str:
    payload = {
        "schema_version": request.schema_version,
        "parent_asset_id": str(request.parent_asset_id),
        "parent_revision": request.parent_revision,
        "parent_content_hash": request.parent_content_hash,
        "operation": request.operation.value,
        "parameters": request.parameters,
        "output_slot": request.output_slot,
        "tool_fingerprint": request.tool_fingerprint,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
