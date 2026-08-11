"""Adapter protocol and deterministic fake providers for contract tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from workbench.contracts.p2_platform import ErrorCategory, StructuredErrorV1

from .models import (
    ProviderCapabilityV1,
    ProviderCostEstimateV1,
    ProviderDescriptorV1,
    ProviderHealthV1,
    ProviderInvocationResultV1,
    ProviderInvocationV1,
)


class ProviderAdapterError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool, failover_allowed: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.failover_allowed = failover_allowed


class ProviderAdapter(Protocol):
    descriptor: ProviderDescriptorV1

    async def probe(self, invocation: ProviderInvocationV1) -> ProviderHealthV1: ...

    async def estimate(self, invocation: ProviderInvocationV1) -> ProviderCostEstimateV1: ...

    async def invoke(self, invocation: ProviderInvocationV1) -> ProviderInvocationResultV1: ...

    async def cancel(self, operation_id: UUID) -> None: ...

    def normalize_error(
        self, error: BaseException, invocation: ProviderInvocationV1
    ) -> StructuredErrorV1: ...


@dataclass
class FakeProviderBehavior:
    delay_ms: int = 0
    failure_mode: str | None = None
    billed_cost_minor: int = 1


class DeterministicFakeProvider:
    """A network-free adapter with explicit failure injection knobs."""

    def __init__(
        self, descriptor: ProviderDescriptorV1, behavior: FakeProviderBehavior | None = None
    ) -> None:
        self.descriptor = descriptor
        self.behavior = behavior or FakeProviderBehavior()
        self.calls: list[ProviderInvocationV1] = []
        self.cancelled: set[UUID] = set()

    async def _delay(self) -> None:
        if self.behavior.delay_ms:
            await asyncio.sleep(self.behavior.delay_ms / 1000)

    def _capability(self, capability_id: str) -> ProviderCapabilityV1:
        for capability in self.descriptor.capabilities:
            if capability.capability_id == capability_id:
                return capability
        raise ProviderAdapterError(
            "capability_not_found",
            "Capability is not registered",
            retryable=False,
            failover_allowed=True,
        )

    async def probe(self, invocation: ProviderInvocationV1) -> ProviderHealthV1:
        await self._delay()
        if self.behavior.failure_mode == "probe_error":
            raise ProviderAdapterError(
                "probe_unavailable", "Fake probe failure", retryable=True, failover_allowed=True
            )
        return ProviderHealthV1(
            provider_id=self.descriptor.provider_id,
            status="available",
            observed_at=invocation.operation.started_at.isoformat().replace("+00:00", "Z"),
            expires_at=invocation.operation.deadline_at.isoformat().replace("+00:00", "Z")
            if invocation.operation.deadline_at
            else invocation.operation.started_at.isoformat().replace("+00:00", "Z"),
            latency_ms_p50=self.behavior.delay_ms,
            latency_ms_p95=self.behavior.delay_ms,
        )

    async def estimate(self, invocation: ProviderInvocationV1) -> ProviderCostEstimateV1:
        await self._delay()
        self._capability(invocation.capability_id)
        if self.behavior.failure_mode == "unknown_billing":
            return ProviderCostEstimateV1(
                provider_id=self.descriptor.provider_id,
                capability_id=invocation.capability_id,
                currency="USD",
                estimated_cost_minor=0,
                price_book_version="fake-unknown",
                confidence="unknown",
                unit="request",
            )
        return ProviderCostEstimateV1(
            provider_id=self.descriptor.provider_id,
            capability_id=invocation.capability_id,
            currency="USD",
            estimated_cost_minor=self.behavior.billed_cost_minor,
            price_book_version="fake-1",
            confidence="exact",
            unit="request",
        )

    async def invoke(self, invocation: ProviderInvocationV1) -> ProviderInvocationResultV1:
        self.calls.append(invocation)
        await self._delay()
        mode = self.behavior.failure_mode
        if mode == "timeout":
            await asyncio.sleep(invocation.operation.budget.timeout_ms / 1000 + 0.05)
        if mode in {"retryable", "permanent", "invalid_response"}:
            raise ProviderAdapterError(
                "fake_" + mode,
                "Deterministic fake failure",
                retryable=mode == "retryable",
                failover_allowed=mode == "retryable",
            )
        self._capability(invocation.capability_id)
        if invocation.operation.operation_id in self.cancelled:
            return ProviderInvocationResultV1(
                operation_id=invocation.operation.operation_id,
                provider_id=self.descriptor.provider_id,
                capability_id=invocation.capability_id,
                status="cancelled",
                cache_identity="sha256:" + "0" * 64,
            )
        return ProviderInvocationResultV1(
            operation_id=invocation.operation.operation_id,
            provider_id=self.descriptor.provider_id,
            capability_id=invocation.capability_id,
            model_resolved=invocation.model,
            status="succeeded",
            output_refs=list(invocation.input_refs),
            usage={"requests": Decimal(1)},
            estimated_cost=Decimal(0),
            billed_cost=Decimal(self.behavior.billed_cost_minor),
            cache_identity="sha256:" + "1" * 64,
            provider_request_id="fake-request",
        )

    async def cancel(self, operation_id: UUID) -> None:
        self.cancelled.add(operation_id)

    def normalize_error(
        self, error: BaseException, invocation: ProviderInvocationV1
    ) -> StructuredErrorV1:
        if isinstance(error, ProviderAdapterError):
            code, retryable, failover_allowed = error.code, error.retryable, error.failover_allowed
            message = str(error)
        else:
            code, retryable, failover_allowed = "provider.adapter_error", False, False
            message = "Provider adapter failed"
        return StructuredErrorV1(
            code=code,
            category=ErrorCategory.PROVIDER,
            message=message,
            retryable=retryable,
            failover_allowed=failover_allowed,
            user_action="Retry or select another provider"
            if failover_allowed
            else "Review provider configuration",
            operation_id=invocation.operation.operation_id,
            attempt_id=invocation.operation.attempt_id,
        )
