"""Provider Kernel data models.

These models are deliberately stricter than any individual vendor SDK. Vendor
responses are normalized at the adapter boundary before they can enter a model.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator

from workbench.contracts.p2_platform import OperationContextV1, _ContractModel

ProviderKind = Literal["llm", "tts", "asr", "ocr", "avatar", "renderer"]
ExecutionMode = Literal["in_process_builtin", "local_process", "remote_https"]


class ProviderCapabilityV1(_ContractModel):
    schema_version: Literal[1] = 1
    capability_id: str = Field(min_length=1, max_length=100)
    modalities: list[str] = Field(min_length=1, max_length=32)
    languages: list[str] = Field(default_factory=list, max_length=256)
    models: list[str] = Field(default_factory=list, max_length=256)
    max_input_bytes: int | None = Field(default=None, ge=0, le=1_099_511_627_776)
    max_duration_us: int | None = Field(default=None, ge=0, le=86_400_000_000)
    supports_streaming: bool = False
    supports_cancellation: bool = False
    supports_idempotency: bool = True
    supports_word_timestamps: bool | None = None
    supports_cost_estimate: bool = False
    data_regions: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("capability_id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not value[0].islower() or any(
            char not in "abcdefghijklmnopqrstuvwxyz0123456789_.-" for char in value
        ):
            raise ValueError("capability_id must be a lowercase contract identifier")
        return value


class ProviderDescriptorV1(_ContractModel):
    schema_version: Literal[1] = 1
    provider_id: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=200)
    kind: ProviderKind
    adapter_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    execution_mode: ExecutionMode
    capabilities: list[ProviderCapabilityV1] = Field(min_length=1, max_length=100)
    credential_schema_id: str | None = Field(default=None, max_length=128)
    privacy_policy_ref: str | None = Field(default=None, max_length=512)
    enabled: bool = True
    trust: Literal["builtin_signed", "builtin_local_process"] = "builtin_signed"

    @field_validator("provider_id")
    @classmethod
    def validate_provider_id(cls, value: str) -> str:
        if not value[0].islower() or any(
            char not in "abcdefghijklmnopqrstuvwxyz0123456789_.-" for char in value
        ):
            raise ValueError("provider_id must be a lowercase contract identifier")
        return value

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, value: list[ProviderCapabilityV1]) -> list[ProviderCapabilityV1]:
        ids = [item.capability_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("provider capabilities must have unique IDs")
        return value


class ProviderInvocationV1(_ContractModel):
    schema_version: Literal[1] = 1
    operation: OperationContextV1
    provider_id: str
    capability_id: str
    model: str | None = Field(default=None, max_length=200)
    input_refs: list[str] = Field(default_factory=list, max_length=10_000)
    parameters: dict[str, Any] = Field(default_factory=dict, max_length=128)
    expected_output_schema: str = Field(min_length=1, max_length=200)

    @field_validator("parameters")
    @classmethod
    def validate_parameter_keys(cls, value: dict[str, Any]) -> dict[str, Any]:
        if any(
            not key
            or key[0].isupper()
            or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_.-" for char in key)
            for key in value
        ):
            raise ValueError("provider parameters must use lowercase namespaced keys")
        return value


class ProviderInvocationResultV1(_ContractModel):
    schema_version: Literal[1] = 1
    operation_id: UUID
    provider_id: str
    capability_id: str
    model_resolved: str | None = None
    status: Literal["succeeded", "failed", "cancelled", "degraded"]
    output_refs: list[str] = Field(default_factory=list, max_length=10_000)
    usage: dict[str, Decimal] = Field(default_factory=dict, max_length=32)
    estimated_cost: Decimal | None = Field(default=None, ge=0)
    billed_cost: Decimal | None = Field(default=None, ge=0)
    cache_identity: str
    provider_request_id: str | None = Field(default=None, max_length=255)
    warnings: list[str] = Field(default_factory=list, max_length=100)


class ProviderAuditEventV1(_ContractModel):
    schema_version: Literal[1] = 1
    event_id: UUID
    operation_id: UUID
    tenant_id: UUID
    project_id: str | None = Field(default=None, max_length=200)
    provider_id: str
    capability_id: str
    event_kind: Literal["invoke", "cache_hit", "failure"]
    status: str = Field(min_length=1, max_length=32)
    billed_cost_minor: int = Field(ge=0)
    occurred_at: datetime
    error_code: str | None = Field(default=None, max_length=100)


class ProviderHealthV1(_ContractModel):
    schema_version: Literal[1] = 1
    provider_id: str
    status: Literal["unknown", "available", "degraded", "disabled", "incompatible"]
    observed_at: str
    expires_at: str
    latency_ms_p50: int | None = Field(default=None, ge=0)
    latency_ms_p95: int | None = Field(default=None, ge=0)
    error_code: str | None = Field(default=None, max_length=100)
    billed_probe: bool = False


class ProviderCostEstimateV1(_ContractModel):
    schema_version: Literal[1] = 1
    provider_id: str
    capability_id: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    estimated_cost_minor: int = Field(ge=0, le=10_000_000_000)
    price_book_version: str = Field(min_length=1, max_length=100)
    confidence: Literal["exact", "estimated", "unknown"]
    unit: str = Field(min_length=1, max_length=100)
