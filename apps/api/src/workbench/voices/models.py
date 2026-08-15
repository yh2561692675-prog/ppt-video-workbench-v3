"""Strict, local-first voice identity and authorization contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from workbench.contracts.p2_platform import _ContractModel, _validate_utc


def _safe_id(value: str, label: str, maximum: int = 128) -> str:
    if not value or len(value) > maximum or value[0] not in "abcdefghijklmnopqrstuvwxyz0123456789":
        raise ValueError(f"{label} must start with a lowercase identifier character")
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_.-" for char in value):
        raise ValueError(f"{label} contains an unsafe character")
    return value


class VoiceAuthorizationV1(_ContractModel):
    schema_version: Literal[1] = 1
    authorization_id: UUID = Field(default_factory=uuid4)
    subject: Literal["self", "licensed_subject"]
    granted_by: str = Field(min_length=1, max_length=200)
    granted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None
    scopes: list[Literal["local_tts", "local_clone", "preview", "export"]] = Field(
        min_length=1, max_length=16
    )
    source_audio_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    consent_note: str | None = Field(default=None, max_length=1000)
    status: Literal["active", "revoked", "expired"] = "active"

    @field_validator("granted_at", "expires_at")
    @classmethod
    def validate_timestamp(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _validate_utc(value)

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("authorization scopes must be unique")
        return value

    @model_validator(mode="after")
    def validate_expiry(self) -> VoiceAuthorizationV1:
        if self.expires_at is not None and self.expires_at <= self.granted_at:
            raise ValueError("expires_at must be after granted_at")
        return self


class VoiceIdentityV1(_ContractModel):
    schema_version: Literal[1] = 1
    voice_id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(min_length=1, max_length=200)
    kind: Literal["local_tts", "local_clone"]
    model_id: str = Field(min_length=1, max_length=128)
    model_revision: str = Field(min_length=1, max_length=200)
    authorization_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["active", "revoked"] = "active"
    local_only: bool = True
    remote_export_allowed: bool = False
    sample_refs: list[str] = Field(default_factory=list, max_length=128)
    output_format: Literal["wav"] = "wav"

    _created_at = field_validator("created_at")(_validate_utc)

    @field_validator("voice_id", "model_id")
    @classmethod
    def validate_ids(cls, value: str, info: object) -> str:
        return _safe_id(value, getattr(info, "field_name", "identifier"))

    @field_validator("model_revision")
    @classmethod
    def validate_revision(cls, value: str) -> str:
        if any(char in value for char in "\\/:"):
            raise ValueError("model_revision must not contain path separators")
        return value

    @model_validator(mode="after")
    def validate_local_boundary(self) -> VoiceIdentityV1:
        if self.local_only and self.remote_export_allowed:
            raise ValueError("local-only voices cannot allow remote export")
        return self
