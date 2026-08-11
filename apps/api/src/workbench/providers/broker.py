"""Provider routing, budget enforcement, idempotency and controlled failover."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from workbench.contracts.p2_platform import ErrorCategory, OperationContextV1, StructuredErrorV1

from .adapter import ProviderAdapter, ProviderAdapterError
from .cache import ProviderCache, cache_identity
from .models import ProviderDescriptorV1, ProviderInvocationResultV1, ProviderInvocationV1
from .policy import DataClassification, ProviderPolicyEvaluator, ProviderPolicyV1
from .registry import ProviderRegistry


@dataclass(frozen=True)
class RouteRequest:
    context: OperationContextV1
    kind: str
    capability_id: str
    input_refs: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    expected_output_schema: str = "provider-output-v1"
    model: str | None = None
    candidate_provider_ids: list[str] | None = None
    fixed_provider_id: str | None = None
    locale: str | None = None
    region: str | None = None
    deterministic_seed: int | None = None
    max_cost_minor: int | None = None
    allow_failover: bool = True
    platform_fingerprint: str | None = None
    runtime_fingerprint: str | None = None
    font_fingerprint: str | None = None
    cloud_revision_id: str | None = None
    policy: ProviderPolicyV1 | None = None
    data_classification: DataClassification = "sensitive"


@dataclass(frozen=True)
class BrokerAttempt:
    provider_id: str
    attempt_id: UUID
    status: str
    error: StructuredErrorV1 | None = None


@dataclass(frozen=True)
class BrokerResult:
    result: ProviderInvocationResultV1
    attempts: tuple[BrokerAttempt, ...]
    cache_hit: bool = False


class ProviderBrokerError(RuntimeError):
    def __init__(
        self, message: str, *, error: StructuredErrorV1, attempts: tuple[BrokerAttempt, ...]
    ) -> None:
        super().__init__(message)
        self.error = error
        self.attempts = attempts


class ProviderBroker:
    def __init__(
        self,
        registry: ProviderRegistry,
        adapters: dict[str, ProviderAdapter],
        *,
        cache: ProviderCache | None = None,
    ) -> None:
        self.registry = registry
        self.adapters = dict(adapters)
        self.cache = cache
        self._idempotency: dict[tuple[UUID, str, UUID], BrokerResult] = {}

    async def invoke(self, request: RouteRequest) -> BrokerResult:
        key = (request.context.tenant_id, request.kind, request.context.idempotency_key)
        previous = self._idempotency.get(key)
        if previous is not None:
            return previous

        candidates = self._candidates(request)
        if not candidates:
            error = self._error(
                request.context,
                "provider.no_candidate",
                "No compatible provider is available",
                retryable=False,
                failover_allowed=False,
            )
            raise ProviderBrokerError(str(error.message), error=error, attempts=())

        attempts: list[BrokerAttempt] = []
        last_error: StructuredErrorV1 | None = None
        for descriptor in candidates:
            adapter = self.adapters.get(descriptor.provider_id)
            if adapter is None:
                continue
            attempt_context = request.context.model_copy(update={"attempt_id": uuid4()})
            invocation = ProviderInvocationV1(
                operation=attempt_context,
                provider_id=descriptor.provider_id,
                capability_id=request.capability_id,
                model=request.model,
                input_refs=request.input_refs,
                parameters=request.parameters,
                expected_output_schema=request.expected_output_schema,
            )
            cached = self._cached_result(request, descriptor.provider_id)
            if cached is not None:
                result = cached.model_copy(
                    update={
                        "operation_id": request.context.operation_id,
                        "provider_id": descriptor.provider_id,
                        "capability_id": request.capability_id,
                    }
                )
                attempts.append(
                    BrokerAttempt(descriptor.provider_id, attempt_context.attempt_id, "cached")
                )
                broker_result = BrokerResult(
                    result=result, attempts=tuple(attempts), cache_hit=True
                )
                self._idempotency[key] = broker_result
                return broker_result
            max_cost_minor = request.max_cost_minor
            if max_cost_minor is None and request.policy is not None:
                max_cost_minor = request.policy.max_cost_minor
            estimate_error = await self._check_budget(adapter, invocation, max_cost_minor)
            if estimate_error is not None:
                attempts.append(
                    BrokerAttempt(
                        descriptor.provider_id,
                        attempt_context.attempt_id,
                        "rejected",
                        estimate_error,
                    )
                )
                last_error = estimate_error
                if request.fixed_provider_id:
                    break
                continue
            try:
                result = await asyncio.wait_for(
                    adapter.invoke(invocation),
                    timeout=attempt_context.budget.timeout_ms / 1000,
                )
            except TimeoutError as error:
                normalized = adapter.normalize_error(
                    ProviderAdapterError(
                        "provider.timeout",
                        "Provider invocation timed out",
                        retryable=True,
                        failover_allowed=True,
                    ),
                    invocation,
                )
                attempts.append(
                    BrokerAttempt(
                        descriptor.provider_id, attempt_context.attempt_id, "timeout", normalized
                    )
                )
                last_error = normalized
            except BaseException as error:
                normalized = adapter.normalize_error(error, invocation)
                attempts.append(
                    BrokerAttempt(
                        descriptor.provider_id, attempt_context.attempt_id, "failed", normalized
                    )
                )
                last_error = normalized
            else:
                identity = cache_identity(
                    provider_id=descriptor.provider_id,
                    capability_id=request.capability_id,
                    adapter_version=descriptor.adapter_version,
                    model_resolved=result.model_resolved,
                    parameters=request.parameters,
                    input_fingerprints=request.input_refs,
                    output_schema_version=request.expected_output_schema,
                    locale=request.locale,
                    region=request.region,
                    deterministic_seed=request.deterministic_seed,
                    tenant_scope=str(request.context.tenant_id),
                    platform_fingerprint=request.platform_fingerprint,
                    runtime_fingerprint=request.runtime_fingerprint,
                    font_fingerprint=request.font_fingerprint,
                    cloud_revision_id=request.cloud_revision_id,
                )
                result = result.model_copy(update={"cache_identity": identity})
                attempts.append(
                    BrokerAttempt(descriptor.provider_id, attempt_context.attempt_id, result.status)
                )
                broker_result = BrokerResult(result=result, attempts=tuple(attempts))
                self._idempotency[key] = broker_result
                if self.cache is not None and result.status in {"succeeded", "degraded"}:
                    self.cache.put(str(request.context.tenant_id), identity, result)
                return broker_result

            if (
                request.fixed_provider_id
                or not request.allow_failover
                or (request.policy is not None and not request.policy.allow_failover)
                or not (last_error and last_error.failover_allowed)
            ):
                break

        if last_error is None:
            last_error = self._error(
                request.context,
                "provider.invoke_failed",
                "Provider invocation failed",
                retryable=False,
                failover_allowed=False,
            )
        raise ProviderBrokerError(
            str(last_error.message), error=last_error, attempts=tuple(attempts)
        )

    def _cached_result(
        self, request: RouteRequest, provider_id: str
    ) -> ProviderInvocationResultV1 | None:
        """Read only deterministic requests from the tenant-scoped cache.

        A missing model may be resolved by the provider, so it is deliberately
        not looked up before invocation. The first call still stores the fully
        resolved identity; callers that need reuse should provide a model.
        """

        if self.cache is None or request.model is None:
            return None
        identity = cache_identity(
            provider_id=provider_id,
            capability_id=request.capability_id,
            adapter_version=self.registry.require(provider_id).adapter_version,
            model_resolved=request.model,
            parameters=request.parameters,
            input_fingerprints=request.input_refs,
            output_schema_version=request.expected_output_schema,
            locale=request.locale,
            region=request.region,
            deterministic_seed=request.deterministic_seed,
            tenant_scope=str(request.context.tenant_id),
            platform_fingerprint=request.platform_fingerprint,
            runtime_fingerprint=request.runtime_fingerprint,
            font_fingerprint=request.font_fingerprint,
            cloud_revision_id=request.cloud_revision_id,
        )
        return self.cache.get(str(request.context.tenant_id), identity)

    async def cancel(self, operation_id: UUID) -> None:
        await asyncio.gather(
            *(adapter.cancel(operation_id) for adapter in self.adapters.values()),
            return_exceptions=True,
        )

    def _candidates(self, request: RouteRequest) -> list[ProviderDescriptorV1]:
        descriptors = self.registry.list(kind=request.kind)
        if request.candidate_provider_ids is not None:
            allowed = set(request.candidate_provider_ids)
            descriptors = [item for item in descriptors if item.provider_id in allowed]
        if request.fixed_provider_id is not None:
            descriptors = [
                item for item in descriptors if item.provider_id == request.fixed_provider_id
            ]
        if request.policy is not None:
            descriptors = ProviderPolicyEvaluator(request.policy).filter(
                descriptors,
                data_classification=request.data_classification,
                region=request.region,
            )
        result = []
        for descriptor in descriptors:
            if descriptor.provider_id not in self.adapters:
                continue
            if not any(
                capability.capability_id == request.capability_id
                for capability in descriptor.capabilities
            ):
                continue
            result.append(descriptor)
        return result

    async def _check_budget(
        self,
        adapter: ProviderAdapter,
        invocation: ProviderInvocationV1,
        max_cost_minor: int | None,
    ) -> StructuredErrorV1 | None:
        if max_cost_minor is None:
            return None
        try:
            estimate = await asyncio.wait_for(
                adapter.estimate(invocation), timeout=invocation.operation.budget.timeout_ms / 1000
            )
        except BaseException as error:
            normalized = adapter.normalize_error(error, invocation)
            return normalized
        if estimate.confidence == "unknown":
            return self._error(
                invocation.operation,
                "provider.cost_unknown",
                "Provider cost could not be estimated",
                retryable=False,
                failover_allowed=True,
            )
        if estimate.estimated_cost_minor > max_cost_minor:
            return self._error(
                invocation.operation,
                "provider.budget_exceeded",
                "Provider estimate exceeds the operation budget",
                retryable=False,
                failover_allowed=True,
            )
        return None

    @staticmethod
    def _error(
        context: OperationContextV1,
        code: str,
        message: str,
        *,
        retryable: bool,
        failover_allowed: bool,
    ) -> StructuredErrorV1:
        return StructuredErrorV1(
            code=code,
            category=ErrorCategory.PROVIDER,
            message=message,
            retryable=retryable,
            failover_allowed=failover_allowed,
            user_action="Retry or select another provider",
            operation_id=context.operation_id,
            attempt_id=context.attempt_id,
        )
