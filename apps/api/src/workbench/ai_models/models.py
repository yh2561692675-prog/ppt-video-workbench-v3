"""Strict contracts for local model descriptors and installations.

The model center is deliberately independent from any model vendor. A model
revision is immutable once it reaches ready; changing a file requires a new
revision and a new manifest.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from workbench.contracts.p2_platform import _ContractModel

ModelKind = Literal["asr", "tts", "voice_clone", "embedding"]
ModelInstallState = Literal[
    "not_installed",
    "queued",
    "downloading",
    "verifying",
    "ready",
    "loading",
    "active",
    "degraded",
    "incompatible",
    "failed",
    "uninstall_pending",
]
ModelDevice = Literal["cpu", "cuda", "directml", "metal", "unknown"]


def _default_supported_devices() -> list[ModelDevice]:
    return ["cpu"]


def _safe_identifier(value: str, *, label: str, maximum: int) -> str:
    if not value or len(value) > maximum:
        raise ValueError(f"{label} must be a non-empty bounded identifier")
    if value[0] not in "abcdefghijklmnopqrstuvwxyz0123456789":
        raise ValueError(f"{label} must start with a lowercase identifier character")
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_.-" for char in value):
        raise ValueError(f"{label} contains an unsafe character")
    return value


class ModelFileV1(_ContractModel):
    schema_version: Literal[1] = 1
    relative_path: str = Field(min_length=1, max_length=512)
    size_bytes: int = Field(gt=0, le=1_099_511_627_776)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        if "\\" in value or value.startswith("/") or ":" in value:
            raise ValueError("model file path must be a relative POSIX path")
        parts = value.split("/")
        if any(not part or part in {".", ".."} for part in parts):
            raise ValueError("model file path contains an unsafe segment")
        return "/".join(parts)


class LocalModelDescriptorV1(_ContractModel):
    schema_version: Literal[1] = 1
    model_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=200)
    kind: ModelKind
    engine: str = Field(min_length=1, max_length=100)
    engine_version: str = Field(min_length=1, max_length=100)
    revision: str = Field(min_length=1, max_length=200)
    source_ref: str = Field(min_length=1, max_length=1024)
    supported_languages: list[str] = Field(default_factory=list, max_length=128)
    capabilities: list[str] = Field(default_factory=list, max_length=128)
    license_ref: str = Field(min_length=1, max_length=512)
    files: list[ModelFileV1] = Field(min_length=1, max_length=256)
    minimum_ram_bytes: int | None = Field(default=None, ge=0)
    recommended_ram_bytes: int | None = Field(default=None, ge=0)
    minimum_vram_bytes: int | None = Field(default=None, ge=0)
    supported_devices: list[ModelDevice] = Field(
        default_factory=_default_supported_devices, max_length=8
    )
    runtime_contract_version: str = Field(pattern=r"^[0-9]+\.[0-9]+$")
    compatible_app_versions: list[str] = Field(default_factory=list, max_length=64)
    remote_download_required: bool = False
    redistribution_allowed: bool = False

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        return _safe_identifier(value, label="model_id", maximum=128)

    @field_validator("supported_languages", "capabilities")
    @classmethod
    def validate_nonempty_items(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("model list fields must not contain empty items")
        return value

    @field_validator("revision")
    @classmethod
    def validate_revision(cls, value: str) -> str:
        if any(char in value for char in "\\/:"):
            raise ValueError("model revision must not contain path separators")
        return value

    @field_validator("files")
    @classmethod
    def validate_unique_files(cls, value: list[ModelFileV1]) -> list[ModelFileV1]:
        paths = [item.relative_path for item in value]
        if len(paths) != len(set(paths)):
            raise ValueError("model files must have unique relative paths")
        return value

    @model_validator(mode="after")
    def validate_memory_order(self) -> LocalModelDescriptorV1:
        if (
            self.minimum_ram_bytes is not None
            and self.recommended_ram_bytes is not None
            and self.minimum_ram_bytes > self.recommended_ram_bytes
        ):
            raise ValueError("minimum RAM must not exceed recommended RAM")
        if self.minimum_vram_bytes is not None and "cpu" in self.supported_devices:
            raise ValueError("CPU models must not require a minimum VRAM")
        return self


class ModelInstallRecordV1(_ContractModel):
    schema_version: Literal[1] = 1
    model_id: str
    revision: str
    status: ModelInstallState
    attempt_id: UUID = Field(default_factory=uuid4)
    bytes_total: int = Field(default=0, ge=0)
    bytes_completed: int = Field(default=0, ge=0)
    manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    installed_at: datetime | None = None
    last_probe_at: datetime | None = None
    last_error_code: str | None = Field(default=None, max_length=100)
    active_lease_count: int = Field(default=0, ge=0)

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        return _safe_identifier(value, label="model_id", maximum=128)

    @field_validator("installed_at", "last_probe_at")
    @classmethod
    def validate_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)
        ):
            raise ValueError("timestamps must include a UTC offset")
        return value.astimezone(UTC) if value is not None else None

    @model_validator(mode="after")
    def validate_progress(self) -> ModelInstallRecordV1:
        if self.bytes_completed > self.bytes_total and self.bytes_total:
            raise ValueError("completed bytes exceed total bytes")
        if self.status in {"ready", "active"} and not self.manifest_sha256:
            raise ValueError("ready models require a manifest hash")
        if self.status in {"ready", "active"} and self.installed_at is None:
            raise ValueError("ready models require installed_at")
        return self


class ModelRuntimeProbeV1(_ContractModel):
    schema_version: Literal[1] = 1
    model_id: str
    revision: str
    status: Literal["available", "missing", "incompatible", "degraded", "failed"]
    device: ModelDevice
    probed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    startup_ms: int | None = Field(default=None, ge=0)
    peak_ram_bytes: int | None = Field(default=None, ge=0)
    peak_vram_bytes: int | None = Field(default=None, ge=0)
    error_code: str | None = Field(default=None, max_length=100)
    warnings: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("probed_at")
    @classmethod
    def validate_probe_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("probed_at must include a UTC offset")
        return value.astimezone(UTC)


class LocalModelRecordV1(_ContractModel):
    schema_version: Literal[1] = 1
    descriptor: LocalModelDescriptorV1
    install: ModelInstallRecordV1
    last_probe: ModelRuntimeProbeV1 | None = None

    @model_validator(mode="after")
    def validate_identity(self) -> LocalModelRecordV1:
        if (
            self.descriptor.model_id != self.install.model_id
            or self.descriptor.revision != self.install.revision
        ):
            raise ValueError("descriptor and install identity must match")
        if self.last_probe is not None and (
            self.last_probe.model_id != self.descriptor.model_id
            or self.last_probe.revision != self.descriptor.revision
        ):
            raise ValueError("probe identity must match descriptor")
        return self
