"""Platform capability and process result models."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from workbench.contracts.p2_platform import _ContractModel


class PlatformInfoV1(_ContractModel):
    schema_version: Literal[1] = 1
    platform: Literal["windows", "macos", "linux"]
    architecture: str = Field(min_length=1, max_length=64)
    runtime_version: str = Field(min_length=1, max_length=100)
    app_version: str = Field(min_length=1, max_length=100)


class ToolInfoV1(_ContractModel):
    schema_version: Literal[1] = 1
    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")
    available: bool
    executable_ref: str | None = Field(default=None, max_length=1024)
    version: str | None = Field(default=None, max_length=100)
    source: Literal["bundled", "supported_system", "unavailable", "unknown"]
    sha256: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    capabilities: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("executable_ref")
    @classmethod
    def validate_logical_reference(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", value):
            raise ValueError("executable_ref must not contain an absolute host path")
        if not re.fullmatch(r"(?:runtime|system|unavailable|unknown)://[a-z0-9_.-]+", value):
            raise ValueError("executable_ref must be a logical tool reference")
        return value


class CapabilityStateV1(_ContractModel):
    schema_version: Literal[1] = 1
    capability_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,99}$")
    status: Literal[
        "supported", "missing", "misconfigured", "temporarily_unavailable", "unsupported"
    ]
    detail: str | None = Field(default=None, max_length=200)


class PlatformCapabilitySnapshotV1(_ContractModel):
    schema_version: Literal[1] = 1
    info: PlatformInfoV1
    capabilities: list[str] = Field(default_factory=list, max_length=200)
    capability_states: list[CapabilityStateV1] = Field(default_factory=list, max_length=200)
    tools: list[ToolInfoV1] = Field(default_factory=list, max_length=100)
    fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    generated_at: str
    expires_at: str

    @field_validator("generated_at", "expires_at")
    @classmethod
    def validate_utc_timestamp(cls, value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("platform snapshot timestamps must be RFC 3339") from error
        if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
            raise ValueError("platform snapshot timestamps must use UTC")
        return parsed.astimezone(UTC).isoformat().replace("+00:00", "Z")

    @model_validator(mode="after")
    def validate_expiry(self) -> PlatformCapabilitySnapshotV1:
        generated = datetime.fromisoformat(self.generated_at.replace("Z", "+00:00"))
        expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        if expires <= generated:
            raise ValueError("platform snapshot expires_at must be after generated_at")
        return self


class ProcessResultV1(_ContractModel):
    schema_version: Literal[1] = 1
    argv: list[str] = Field(min_length=1, max_length=1000)
    return_code: int
    stdout: str = Field(max_length=1_000_000)
    stderr: str = Field(max_length=1_000_000)
    timed_out: bool = False
    cancelled: bool = False
    output_truncated: bool = False
    duration_ms: int = Field(ge=0)


class PlatformPathError(ValueError):
    pass


class ProcessServiceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
