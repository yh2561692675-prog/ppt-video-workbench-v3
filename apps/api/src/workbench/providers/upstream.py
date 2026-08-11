"""Reviewed built-in adapters for the existing business-service seams.

The adapters accept an injected callable rather than importing vendor SDKs or
executing task-provided code. This lets the existing LLM/ASR/TTS/OCR/renderer
services migrate one at a time while preserving their public service methods.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from workbench.contracts.p2_platform import (
    BudgetV1,
    ErrorCategory,
    OperationContextV1,
    StructuredErrorV1,
)

from .adapter import ProviderAdapter, ProviderAdapterError
from .broker import ProviderBroker, RouteRequest
from .models import (
    ProviderCapabilityV1,
    ProviderCostEstimateV1,
    ProviderDescriptorV1,
    ProviderHealthV1,
    ProviderInvocationResultV1,
    ProviderInvocationV1,
)

BuiltinHandler = Callable[[ProviderInvocationV1], object | Awaitable[object]]


class BuiltinArtifactStore:
    """Bounded in-memory bridge for local adapter outputs.

    Provider contracts expose only logical artifact references. The local
    migration seam keeps the small response payload available to the legacy
    caller without putting provider text or bytes into the contract result.
    """

    def __init__(self, *, max_entries: int = 1_024, max_bytes: int = 64 * 1024 * 1024) -> None:
        if max_entries < 1 or max_bytes < 1:
            raise ValueError("artifact store limits must be positive")
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self._values: dict[str, str | bytes] = {}
        self._bytes = 0

    def put(self, value: str | bytes) -> str:
        raw = value.encode("utf-8") if isinstance(value, str) else value
        if len(raw) > self.max_bytes:
            raise ProviderAdapterError(
                "provider.output_too_large",
                "Provider output exceeds the local artifact bridge limit",
                retryable=False,
                failover_allowed=False,
            )
        reference = "artifact://sha256:" + hashlib.sha256(raw).hexdigest()
        previous = self._values.pop(reference, None)
        if previous is not None:
            self._bytes -= len(previous.encode("utf-8") if isinstance(previous, str) else previous)
        while self._values and (
            len(self._values) >= self.max_entries or self._bytes + len(raw) > self.max_bytes
        ):
            _, evicted = self._values.popitem()
            self._bytes -= len(evicted.encode("utf-8") if isinstance(evicted, str) else evicted)
        self._values[reference] = value
        self._bytes += len(raw)
        return reference

    def get(self, reference: str) -> str | bytes:
        try:
            return self._values[reference]
        except KeyError as error:
            raise ProviderAdapterError(
                "provider.artifact_missing",
                "Provider artifact is no longer available in the local bridge",
                retryable=False,
                failover_allowed=False,
            ) from error


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

    def __init__(
        self,
        descriptor: ProviderDescriptorV1,
        handler: BuiltinHandler,
        *,
        artifact_store: BuiltinArtifactStore | None = None,
    ) -> None:
        self.descriptor = descriptor
        self.handler = handler
        self.artifact_store = artifact_store
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
            reference = (
                self.artifact_store.put(value)
                if self.artifact_store is not None
                else "artifact://sha256:" + hashlib.sha256(value).hexdigest()
            )
            return self._result(invocation, "succeeded", [reference])
        if isinstance(value, str):
            reference = (
                self.artifact_store.put(value)
                if self.artifact_store is not None
                else "artifact://sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
            )
            return self._result(invocation, "succeeded", [reference])
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


def create_llm_handler(client: object, profiles: object) -> BuiltinHandler:
    """Adapt the existing profile-backed LLM client to the Provider Kernel."""

    def handle(invocation: ProviderInvocationV1) -> object:
        from uuid import UUID

        profile_value = invocation.parameters.get("llm.profile_id")
        messages = invocation.parameters.get("llm.messages")
        if not isinstance(profile_value, str) or not isinstance(messages, list):
            raise ProviderAdapterError(
                "llm.invalid_parameters",
                "LLM provider parameters are incomplete",
                retryable=False,
                failover_allowed=False,
            )
        profile_id = UUID(profile_value)
        credentials = profiles.credentials(profile_id)  # type: ignore[attr-defined]
        complete = client.complete  # type: ignore[attr-defined]
        max_tokens = invocation.parameters.get("llm.max_tokens")
        return complete(
            base_url=str(credentials.profile.base_url).rstrip("/"),
            api_key=credentials.api_key,
            model=invocation.model or credentials.profile.model,
            messages=messages,
            max_tokens=int(max_tokens) if isinstance(max_tokens, int) else None,
        )

    return handle


class BrokerCompletionClient:
    """CompletionClient-compatible facade for the opt-in provider route."""

    def __init__(
        self,
        broker: ProviderBroker,
        artifacts: BuiltinArtifactStore,
        *,
        tenant_id: UUID,
        profile_id: UUID,
    ) -> None:
        self.broker = broker
        self.artifacts = artifacts
        self.tenant_id = tenant_id
        self.profile_id = profile_id

    def complete(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
    ) -> str:
        del base_url, api_key
        now = datetime.now(UTC)
        context = OperationContextV1(
            operation_id=uuid4(),
            idempotency_key=uuid4(),
            attempt_id=uuid4(),
            tenant_id=self.tenant_id,
            request_kind="provider.invoke",
            started_at=now,
            deadline_at=now + timedelta(seconds=120),
            budget=BudgetV1(timeout_ms=120_000),
        )
        request = RouteRequest(
            context=context,
            kind="llm",
            capability_id="completion",
            model=model,
            parameters={
                "llm.profile_id": str(self.profile_id),
                "llm.messages": messages,
                "llm.max_tokens": max_tokens or 0,
            },
            expected_output_schema="text-v1",
            fixed_provider_id="builtin-llm",
            allow_failover=False,
        )
        result = asyncio.run(self.broker.invoke(request)).result
        if result.status != "succeeded" or not result.output_refs:
            raise RuntimeError("LLM provider returned no text artifact")
        value = self.artifacts.get(result.output_refs[0])
        if not isinstance(value, str):
            raise RuntimeError("LLM provider returned a non-text artifact")
        return value
