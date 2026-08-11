"""Strict, dependency-light P2 platform contracts and canonical JSON helpers.

The contracts remain independently testable and are installed through the opt-in
P2 composition root; legacy flags keep the existing application path unchanged.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
_RESOURCE_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
_SAFE_KEY_RE = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class ErrorCategory(StrEnum):
    PROVIDER = "provider"
    PLATFORM = "platform"
    SYNC = "sync"
    CLOUD = "cloud"
    EXECUTOR = "executor"
    VALIDATION = "validation"


class BudgetV1(_ContractModel):
    schema_version: Literal[1] = 1
    timeout_ms: int = Field(ge=1, le=86_400_000)
    max_attempts: int = Field(default=1, ge=1, le=10)
    max_input_bytes: int = Field(default=1_073_741_824, ge=0, le=1_099_511_627_776)
    max_output_bytes: int = Field(default=4_294_967_296, ge=0, le=1_099_511_627_776)
    max_cost_minor: int | None = Field(default=None, ge=0, le=10_000_000_000)


def _validate_uuid(value: UUID | str) -> UUID:
    parsed = value if isinstance(value, UUID) else UUID(value)
    if not _UUID_RE.fullmatch(str(parsed)):
        raise ValueError("UUID must use lowercase RFC 4122 hyphen format")
    return parsed


def _validate_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must include UTC offset")
    return value.astimezone(UTC)


def normalize_logical_path(value: str) -> str:
    """Validate a portable project path and return its normalized POSIX form."""

    if not value or "\x00" in value or "\\" in value:
        raise ValueError("logical_path must be a non-empty POSIX relative path")
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise ValueError("logical_path must not be absolute")
    path = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("logical_path contains an unsafe segment")
    if any(":" in part for part in path.parts):
        raise ValueError("logical_path must not contain drive or stream syntax")
    normalized = "/".join(path.parts)
    if len(normalized) > 1024:
        raise ValueError("logical_path is too long")
    return normalized


class LogicalResourceRefV1(_ContractModel):
    schema_version: Literal[1] = 1
    tenant_id: UUID
    resource_type: str = Field(min_length=1, max_length=64)
    resource_id: UUID
    logical_path: str | None = Field(default=None, max_length=1024)
    revision_id: UUID | None = None

    _tenant_uuid = field_validator("tenant_id", "resource_id", "revision_id", mode="before")(
        _validate_uuid
    )

    @field_validator("resource_type")
    @classmethod
    def validate_resource_type(cls, value: str) -> str:
        if not _RESOURCE_RE.fullmatch(value):
            raise ValueError("resource_type must be a lowercase contract identifier")
        return value

    @field_validator("logical_path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        return None if value is None else normalize_logical_path(value)


class OperationContextV1(_ContractModel):
    schema_version: Literal[1] = 1
    operation_id: UUID
    idempotency_key: UUID
    attempt_id: UUID
    tenant_id: UUID
    actor_id: UUID | None = None
    request_kind: str = Field(min_length=1, max_length=100)
    started_at: datetime
    deadline_at: datetime | None = None
    budget: BudgetV1
    resource: LogicalResourceRefV1 | None = None

    _ids = field_validator(
        "operation_id", "idempotency_key", "attempt_id", "tenant_id", "actor_id", mode="before"
    )(_validate_uuid)
    _timestamps = field_validator("started_at", "deadline_at")(_validate_utc)

    @field_validator("request_kind")
    @classmethod
    def validate_request_kind(cls, value: str) -> str:
        if not _SAFE_KEY_RE.fullmatch(value):
            raise ValueError("request_kind must be a lowercase contract identifier")
        return value

    @model_validator(mode="after")
    def validate_deadline(self) -> OperationContextV1:
        if self.deadline_at is not None and self.deadline_at <= self.started_at:
            raise ValueError("deadline_at must be after started_at")
        return self


class StructuredErrorV1(_ContractModel):
    schema_version: Literal[1] = 1
    code: str = Field(min_length=1, max_length=100)
    category: ErrorCategory
    message: str = Field(min_length=1, max_length=500)
    retryable: bool
    failover_allowed: bool
    user_action: str = Field(min_length=1, max_length=500)
    safe_details: dict[str, str | int | bool | None] = Field(default_factory=dict, max_length=32)
    provider_id: str | None = Field(default=None, max_length=100)
    operation_id: UUID
    attempt_id: UUID | None = None

    _ids = field_validator("operation_id", "attempt_id", mode="before")(_validate_uuid)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not _SAFE_KEY_RE.fullmatch(value):
            raise ValueError("code must be a lowercase contract identifier")
        return value

    @field_validator("safe_details")
    @classmethod
    def validate_safe_details(
        cls, value: dict[str, str | int | bool | None]
    ) -> dict[str, str | int | bool | None]:
        if any(not _SAFE_KEY_RE.fullmatch(key) for key in value):
            raise ValueError("safe_details keys must be lowercase contract identifiers")
        return value


def _canonicalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="python", exclude_none=True))
    if isinstance(value, Mapping):
        return {
            unicodedata.normalize("NFC", str(key)): _canonicalize(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return _validate_utc(value).isoformat().replace("+00:00", "Z")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite Decimal is not canonical JSON")
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite float is not canonical JSON")
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if value is None or isinstance(value, (bool, int)):
        return value
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json(value: BaseModel | Mapping[str, Any]) -> str:
    """Return deterministic UTF-8-ready canonical JSON text."""

    normalized = _canonicalize(value)
    return json.dumps(normalized, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def canonical_sha256(value: BaseModel | Mapping[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
