"""Reviewed built-in adapters for the existing business-service seams.

The adapters accept an injected callable rather than importing vendor SDKs or
executing task-provided code. This lets the existing LLM/ASR/TTS/OCR/renderer
services migrate one at a time while preserving their public service methods.
"""

from __future__ import annotations

import hashlib
import inspect
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from workbench.contracts.p2_platform import ErrorCategory, StructuredErrorV1

from .adapter import ProviderAdapter, ProviderAdapterError
from .models import (
    ProviderCapabilityV1,
    ProviderCostEstimateV1,
    ProviderDescriptorV1,
    ProviderHealthV1,
    ProviderInvocationResultV1,
    ProviderInvocationV1,
)

BuiltinHandler = Callable[[ProviderInvocationV1], object | Awaitable[object]]


@dataclass(frozen=True)
class BuiltinProviderSpec:
    provider_id: str
    display_name: str
    kind: str
    capability_id: str
    output_schema: str
    media_type: str


BUILTIN_PROVIDER_SPECS: tuple[BuiltinProviderSpec, ...] = (
    BuiltinProviderSpec(
        "builtin-llm", "Built-in LLM seam", "llm", "completion", "text-v1", "text/plain"
    ),
    BuiltinProviderSpec(
        "builtin-asr",
        "Built-in ASR seam",
        "asr",
        "transcription",
        "transcript-v1",
        "application/json",
    ),
    BuiltinProviderSpec(
        "builtin-tts", "Built-in TTS seam", "tts", "speech.synthesize", "audio-v1", "audio/wav"
    ),
    BuiltinProviderSpec(
        "builtin-avatar",
        "Built-in avatar seam",
        "avatar",
        "avatar.generate",
        "video-v1",
        "video/mp4",
    ),
    BuiltinProviderSpec(
        "builtin-ocr", "Built-in OCR seam", "ocr", "text.extract", "ocr-v1", "application/json"
    ),
    BuiltinProviderSpec(
        "builtin-renderer",
        "Built-in renderer seam",
        "renderer",
        "render.page",
        "render-v1",
        "video/mp4",
    ),
)


def builtin_descriptors() -> list[ProviderDescriptorV1]:
    """Return only reviewed, static descriptors for the six upstream seams."""

    return [
        ProviderDescriptorV1(
            provider_id=spec.provider_id,
            display_name=spec.display_name,
            kind=spec.kind,  # type: ignore[arg-type]
            adapter_version="1.0.0",
            execution_mode="in_process_builtin",
            capabilities=[
                ProviderCapabilityV1(
                    capability_id=spec.capability_id,
                    modalities=[spec.kind],
                    supports_cancellation=True,
                    supports_cost_estimate=True,
                    supports_idempotency=True,
                )
            ],
        )
        for spec in BUILTIN_PROVIDER_SPECS
    ]


class BuiltinProviderAdapter(ProviderAdapter):
    """Normalize an injected existing-service callable into Provider Kernel output."""

    def __init__(self, descriptor: ProviderDescriptorV1, handler: BuiltinHandler) -> None:
        self.descriptor = descriptor
        self.handler = handler
        self.cancelled: set[UUID] = set()

    async def probe(self, invocation: ProviderInvocationV1) -> ProviderHealthV1:
        self._validate_invocation(invocation)
        now = invocation.operation.started_at.isoformat().replace("+00:00", "Z")
        expiry = (
            invocation.operation.deadline_at.isoformat().replace("+00:00", "Z")
            if invocation.operation.deadline_at
            else now
        )
        return ProviderHealthV1(
            provider_id=self.descriptor.provider_id,
            status="available",
            observed_at=now,
            expires_at=expiry,
            latency_ms_p50=0,
            latency_ms_p95=0,
        )

    async def estimate(self, invocation: ProviderInvocationV1) -> ProviderCostEstimateV1:
        self._validate_invocation(invocation)
        return ProviderCostEstimateV1(
            provider_id=self.descriptor.provider_id,
            capability_id=invocation.capability_id,
            currency="USD",
            estimated_cost_minor=0,
            price_book_version="builtin-1",
            confidence="estimated",
            unit="request",
        )

    async def invoke(self, invocation: ProviderInvocationV1) -> ProviderInvocationResultV1:
        self._validate_invocation(invocation)
        if invocation.operation.operation_id in self.cancelled:
            return self._result(invocation, "cancelled", [])
        try:
            value = self.handler(invocation)
            if inspect.isawaitable(value):
                value = await value
            return self._normalize_output(invocation, value)
        except ProviderAdapterError:
            raise
        except (OSError, RuntimeError, ValueError, TypeError) as error:
            raise ProviderAdapterError(
                f"{self.descriptor.kind}.adapter_error",
                "Built-in provider adapter failed",
                retryable=isinstance(error, (OSError, RuntimeError)),
                failover_allowed=isinstance(error, (OSError, RuntimeError)),
            ) from error

    async def cancel(self, operation_id: UUID) -> None:
        self.cancelled.add(operation_id)

    def normalize_error(
        self, error: BaseException, invocation: ProviderInvocationV1
    ) -> StructuredErrorV1:
        if isinstance(error, ProviderAdapterError):
            code = error.code
            retryable = error.retryable
            failover = error.failover_allowed
        else:
            code = f"{self.descriptor.kind}.adapter_error"
            retryable = False
            failover = False
        return StructuredErrorV1(
            code=code,
            category=ErrorCategory.PROVIDER,
            message="Built-in provider operation failed",
            retryable=retryable,
            failover_allowed=failover,
            user_action="Retry or review the local provider configuration",
            operation_id=invocation.operation.operation_id,
            attempt_id=invocation.operation.attempt_id,
        )

    def _validate_invocation(self, invocation: ProviderInvocationV1) -> None:
        if invocation.provider_id != self.descriptor.provider_id:
            raise ProviderAdapterError(
                "provider.scope_mismatch",
                "Invocation provider does not match adapter",
                retryable=False,
                failover_allowed=False,
            )
        if invocation.capability_id not in {
            capability.capability_id for capability in self.descriptor.capabilities
        }:
            raise ProviderAdapterError(
                "provider.capability_not_found",
                "Invocation capability is not registered",
                retryable=False,
                failover_allowed=False,
            )
        for ref in invocation.input_refs:
            if ref.startswith(("/", "\\", "file:", "C:", "F:", "D:")):
                raise ProviderAdapterError(
                    "provider.absolute_path_rejected",
                    "Provider input references must be logical or content-addressed",
                    retryable=False,
                    failover_allowed=False,
                )

    def _normalize_output(
        self, invocation: ProviderInvocationV1, value: object
    ) -> ProviderInvocationResultV1:
        if isinstance(value, ProviderInvocationResultV1):
            if value.provider_id != self.descriptor.provider_id:
                raise ProviderAdapterError(
                    "provider.invalid_response",
                    "Adapter returned a foreign provider result",
                    retryable=False,
                    failover_allowed=False,
                )
            return value.model_copy(update={"operation_id": invocation.operation.operation_id})
        if isinstance(value, bytes):
            digest = "sha256:" + hashlib.sha256(value).hexdigest()
            return self._result(invocation, "succeeded", [f"artifact://{digest}"])
        if isinstance(value, str):
            digest = "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
            return self._result(invocation, "succeeded", [f"artifact://{digest}"])
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
            refs = [str(item) for item in value]
            if any(ref.startswith(("/", "\\", "file:", "C:", "F:", "D:")) for ref in refs):
                raise ProviderAdapterError(
                    "provider.absolute_path_rejected",
                    "Provider outputs must use logical artifact references",
                    retryable=False,
                    failover_allowed=False,
                )
            return self._result(invocation, "succeeded", refs)
        raise ProviderAdapterError(
            "provider.invalid_response",
            "Built-in provider returned an unsupported response",
            retryable=False,
            failover_allowed=False,
        )

    def _result(
        self,
        invocation: ProviderInvocationV1,
        status: str,
        output_refs: list[str],
    ) -> ProviderInvocationResultV1:
        return ProviderInvocationResultV1(
            operation_id=invocation.operation.operation_id,
            provider_id=self.descriptor.provider_id,
            capability_id=invocation.capability_id,
            model_resolved=invocation.model,
            status=status,  # type: ignore[arg-type]
            output_refs=output_refs,
            usage={"requests": Decimal(1)},
            estimated_cost=Decimal(0),
            billed_cost=Decimal(0),
            cache_identity="sha256:" + "0" * 64,
        )
