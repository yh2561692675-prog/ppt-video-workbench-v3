"""Platform capability and process result models."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

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


class PlatformCapabilitySnapshotV1(_ContractModel):
    schema_version: Literal[1] = 1
    info: PlatformInfoV1
    capabilities: list[str] = Field(default_factory=list, max_length=200)
    tools: list[ToolInfoV1] = Field(default_factory=list, max_length=100)
    fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    generated_at: str


class ProcessResultV1(_ContractModel):
    schema_version: Literal[1] = 1
    argv: list[str] = Field(min_length=1, max_length=1000)
    return_code: int
    stdout: str = Field(max_length=1_000_000)
    stderr: str = Field(max_length=1_000_000)
    timed_out: bool = False
    cancelled: bool = False
    duration_ms: int = Field(ge=0)


class PlatformPathError(ValueError):
    pass


class ProcessServiceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
