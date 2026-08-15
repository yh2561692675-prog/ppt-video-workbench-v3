"""Versioned provider contracts shared by local and remote adapters.

V2 is additive: the existing V1 broker remains the execution path while these
contracts carry the metadata needed for deterministic routing, billing and
auditable candidate outputs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from workbench.contracts.p2_platform import _ContractModel, _validate_utc

ProviderDataClass = Literal["public", "internal", "sensitive", "restricted"]
ProviderOperationStatus = Literal[
    "queued", "running", "succeeded", "failed", "cancelled", "unknown_billed"
]


def _identifier(value: str, *, label: str, maximum: int = 128) -> str:
    if not value or len(value) > maximum:
        raise ValueError(f"{label} must be a non-empty bounded identifier")
    if value[0] not in "abcdefghijklmnopqrstuvwxyz0123456789":
        raise ValueError(f"{label} must start with a lowercase character")
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_.-" for char in value):
        raise ValueError(f"{label} contains an unsafe character")
    return value


class ProviderRoutePolicyV2(_ContractModel):
    schema_version: Literal[2] = 2
    policy_id: str = Field(min_length=1, max_length=128)
    policy_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    capability_id: str = Field(min_length=1, max_length=100)
    allowed_provider_ids: list[str] | None = Field(default=None, max_length=100)
    fixed_provider_id: str | None = Field(default=None, max_length=128)
    credential_ref: str | None = Field(default=None, max_length=200)
    price_book_version: str | None = Field(default=None, max_length=100)
    data_classification: ProviderDataClass = "sensitive"
    allowed_regions: list[str] = Field(default_factory=list, max_length=100)
    allow_remote_https: bool = False
    allow_failover: bool = False
    max_cost_minor: int | None = Field(default=None, ge=0)
    retention_class: Literal["none", "ephemeral", "provider_defined", "persistent"] = "none"
    require_idempotency: bool = True

    @field_validator("policy_id", "capability_id")
    @classmethod
    def validate_ids(cls, value: str, info: object) -> str:
        field_name = getattr(info, "field_name", "identifier")
        return _identifier(value, label=field_name)

    @field_validator("allowed_provider_ids")
    @classmethod
    def validate_allowlist(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = [_identifier(item, label="provider_id") for item in value]
        if len(normalized) != len(set(normalized)):
            raise ValueError("allowed_provider_ids must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_fixed_provider(self) -> ProviderRoutePolicyV2:
        if self.fixed_provider_id is not None:
            _identifier(self.fixed_provider_id, label="fixed_provider_id")
            if (
                self.allowed_provider_ids is not None
                and self.fixed_provider_id not in self.allowed_provider_ids
            ):
                raise ValueError("fixed provider must be in allowed_provider_ids")
        if self.allow_remote_https and self.data_classification == "restricted":
            raise ValueError("restricted data cannot use remote HTTPS")
        return self


class ProviderOperationV2(_ContractModel):
    schema_version: Literal[2] = 2
    operation_id: UUID
    attempt_id: UUID
    idempotency_key: UUID
    provider_id: str
    capability_id: str
    operation_kind: Literal["llm", "asr", "tts", "ocr", "avatar", "renderer"]
    policy_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    credential_ref: str | None = Field(default=None, max_length=200)
    model_requested: str | None = Field(default=None, max_length=200)
    model_resolved: str | None = Field(default=None, max_length=200)
    input_refs: list[str] = Field(default_factory=list, max_length=10_000)
    output_refs: list[str] = Field(default_factory=list, max_length=10_000)
    expected_output_schema: str = Field(min_length=1, max_length=200)
    input_data_classification: ProviderDataClass = "sensitive"
    status: ProviderOperationStatus = "queued"
    usage: dict[str, Decimal] = Field(default_factory=dict, max_length=64)
    estimated_cost_minor: int | None = Field(default=None, ge=0)
    billed_cost_minor: int | None = Field(default=None, ge=0)
    billing_state: Literal["none", "known", "unknown"] = "none"
    provider_request_id: str | None = Field(default=None, max_length=255)
    cache_identity: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list, max_length=100)

    _timestamps = field_validator("started_at", "finished_at")(_validate_utc)

    @field_validator("provider_id", "capability_id")
    @classmethod
    def validate_ids(cls, value: str, info: object) -> str:
        return _identifier(value, label=getattr(info, "field_name", "identifier"), maximum=128)

    @model_validator(mode="after")
    def validate_billing(self) -> ProviderOperationV2:
        if self.billing_state == "known" and self.billed_cost_minor is None:
            raise ValueError("known billing state requires billed_cost_minor")
        if self.billing_state == "unknown" and self.status not in {"failed", "unknown_billed"}:
            raise ValueError("unknown billing state is only valid for failed operations")
        if self.finished_at is not None and self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        return self


class AdapterConformanceResultV1(_ContractModel):
    schema_version: Literal[1] = 1
    adapter_id: str = Field(min_length=1, max_length=128)
    descriptor_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    tested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: Literal["pass", "fail", "degraded"]
    checks: dict[str, Literal["pass", "fail", "skip"]] = Field(min_length=1, max_length=64)
    error_codes: list[str] = Field(default_factory=list, max_length=64)
    sanitized: bool = True
    fake_provider: bool = True

    _tested_at = field_validator("tested_at")(_validate_utc)

    @field_validator("adapter_id")
    @classmethod
    def validate_adapter_id(cls, value: str) -> str:
        return _identifier(value, label="adapter_id")

    @model_validator(mode="after")
    def validate_status(self) -> AdapterConformanceResultV1:
        if self.status == "pass" and any(value == "fail" for value in self.checks.values()):
            raise ValueError("a passing conformance result cannot contain failed checks")
        return self
