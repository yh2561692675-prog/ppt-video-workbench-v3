"""Standalone Provider API router used by the settings UI and diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import Field

from workbench.contracts.p2_platform import (
    BudgetV1,
    OperationContextV1,
    _ContractModel,
    canonical_sha256,
)

from .adapter import ProviderAdapter
from .models import ProviderCostEstimateV1
from .policy import ProviderPolicyV1
from .probe import CapabilityProbeService, ProbeMode
from .registry import ProviderRegistry


class ProviderProbeRequest(_ContractModel):
    tenant_id: UUID
    capability_id: str = Field(min_length=1, max_length=100)
    mode: ProbeMode = "health"
    confirm_billed_sample: bool = False
    force: bool = False
    timeout_ms: int = Field(default=10_000, ge=100, le=86_400_000)


class ProviderEstimateRequest(_ContractModel):
    tenant_id: UUID
    capability_id: str = Field(min_length=1, max_length=100)
    provider_id: str
    parameters: dict[str, object] = Field(default_factory=dict, max_length=128)
    timeout_ms: int = Field(default=10_000, ge=100, le=86_400_000)


class ProviderInvokeRequest(_ContractModel):
    tenant_id: UUID
    capability_id: str = Field(min_length=1, max_length=100)
    model: str | None = Field(default=None, max_length=200)
    input_refs: list[str] = Field(default_factory=list, max_length=10_000)
    parameters: dict[str, object] = Field(default_factory=dict, max_length=128)
    expected_output_schema: str = Field(min_length=1, max_length=200)
    timeout_ms: int = Field(default=120_000, ge=100, le=86_400_000)


class ProviderCancelRequest(_ContractModel):
    operation_id: UUID


class ProviderPolicyUpdate(_ContractModel):
    policy: ProviderPolicyV1


@dataclass
class ProviderApiState:
    registry: ProviderRegistry
    adapters: dict[str, ProviderAdapter]
    probe_service: CapabilityProbeService = field(default_factory=CapabilityProbeService)
    policies: dict[tuple[str, str], ProviderPolicyV1] = field(default_factory=dict)
    usage_minor: dict[tuple[str, str], int] = field(default_factory=dict)
    health: dict[tuple[str, str], object] = field(default_factory=dict)


def create_provider_router(state: ProviderApiState) -> APIRouter:
    router = APIRouter(prefix="/providers", tags=["providers"])

    @router.get("")
    async def list_providers(
        response: Response, if_none_match: str | None = Header(default=None)
    ) -> object:
        descriptors = state.registry.list()
        etag = canonical_sha256(
            {"providers": [item.model_dump(mode="json") for item in descriptors]}
        )
        response.headers["ETag"] = etag
        if if_none_match == etag:
            response.status_code = 304
            return Response(status_code=304, headers={"ETag": etag})
        return descriptors

    @router.get("/capabilities")
    async def list_capabilities() -> list[dict[str, object]]:
        return [
            {
                "provider_id": descriptor.provider_id,
                "kind": descriptor.kind,
                "capability": capability.model_dump(mode="json"),
            }
            for descriptor in state.registry.list()
            for capability in descriptor.capabilities
        ]

    @router.post("/{provider_id}/probe")
    async def probe_provider(provider_id: str, request: ProviderProbeRequest) -> object:
        adapter = state.adapters.get(provider_id)
        if adapter is None or state.registry.get(provider_id) is None:
            raise HTTPException(status_code=404, detail="provider_not_found")
        context = _context(request.tenant_id, "provider.probe", request.timeout_ms)
        try:
            snapshot = await state.probe_service.probe(
                adapter,
                context,
                capability_id=request.capability_id,
                mode=request.mode,
                confirm_billed_sample=request.confirm_billed_sample,
                force=request.force,
            )
        except PermissionError as error:
            raise HTTPException(status_code=409, detail="sample_confirmation_required") from error
        except Exception as error:
            raise HTTPException(status_code=502, detail="provider_probe_failed") from error
        state.health[(provider_id, request.capability_id)] = snapshot
        return snapshot

    @router.get("/health")
    async def list_health() -> list[object]:
        return list(state.health.values())

    @router.post("/{provider_id}/invoke")
    async def invoke_provider(
        provider_id: str, request: ProviderInvokeRequest
    ) -> object:
        adapter = state.adapters.get(provider_id)
        descriptor = state.registry.get(provider_id)
        if adapter is None or descriptor is None:
            raise HTTPException(status_code=404, detail="provider_not_found")
        context = _context(request.tenant_id, "provider.invoke", request.timeout_ms)
        from .models import ProviderInvocationV1

        invocation = ProviderInvocationV1(
            operation=context,
            provider_id=provider_id,
            capability_id=request.capability_id,
            model=request.model,
            input_refs=request.input_refs,
            parameters=request.parameters,
            expected_output_schema=request.expected_output_schema,
        )
        try:
            return await adapter.invoke(invocation)
        except Exception as error:
            normalized = adapter.normalize_error(error, invocation)
            raise HTTPException(
                status_code=502,
                detail=normalized.model_dump(mode="json"),
            ) from error

    @router.post("/{provider_id}/cancel")
    async def cancel_provider(
        provider_id: str, request: ProviderCancelRequest
    ) -> dict[str, object]:
        adapter = state.adapters.get(provider_id)
        if adapter is None or state.registry.get(provider_id) is None:
            raise HTTPException(status_code=404, detail="provider_not_found")
        await adapter.cancel(request.operation_id)
        return {
            "provider_id": provider_id,
            "operation_id": str(request.operation_id),
            "status": "cancel_requested",
        }

    @router.post("/estimate", response_model=ProviderCostEstimateV1)
    async def estimate_provider(request: ProviderEstimateRequest) -> ProviderCostEstimateV1:
        adapter = state.adapters.get(request.provider_id)
        descriptor = state.registry.get(request.provider_id)
        if adapter is None or descriptor is None:
            raise HTTPException(status_code=404, detail="provider_not_found")
        context = _context(request.tenant_id, "provider.estimate", request.timeout_ms)
        from .models import ProviderInvocationV1

        try:
            return await adapter.estimate(
                ProviderInvocationV1(
                    operation=context,
                    provider_id=request.provider_id,
                    capability_id=request.capability_id,
                    parameters=request.parameters,
                    expected_output_schema="provider-estimate-v1",
                )
            )
        except Exception as error:
            raise HTTPException(status_code=502, detail="provider_estimate_failed") from error

    @router.get("/projects/{project_id}/policy")
    async def get_policy(project_id: str, tenant_id: UUID) -> ProviderPolicyV1:
        return state.policies.get((str(tenant_id), project_id), ProviderPolicyV1())

    @router.put("/projects/{project_id}/policy")
    async def put_policy(
        project_id: str, tenant_id: UUID, update: ProviderPolicyUpdate
    ) -> ProviderPolicyV1:
        state.policies[(str(tenant_id), project_id)] = update.policy
        return update.policy

    @router.get("/projects/{project_id}/usage")
    async def get_usage(project_id: str, tenant_id: UUID) -> dict[str, object]:
        return {
            "tenant_id": str(tenant_id),
            "project_id": project_id,
            "billed_minor": state.usage_minor.get((str(tenant_id), project_id), 0),
            "currency": "USD",
        }

    return router


def _context(tenant_id: UUID, request_kind: str, timeout_ms: int) -> OperationContextV1:
    now = datetime.now(UTC)
    return OperationContextV1(
        operation_id=uuid4(),
        idempotency_key=uuid4(),
        attempt_id=uuid4(),
        tenant_id=tenant_id,
        request_kind=request_kind,
        started_at=now,
        deadline_at=now + timedelta(milliseconds=timeout_ms),
        budget=BudgetV1(timeout_ms=timeout_ms),
    )
