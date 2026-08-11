"""Standalone Provider API router used by the settings UI and diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from math import ceil
from typing import Literal
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
from .billing import ProviderRateLimiter
from .broker import ProviderBroker, ProviderBrokerError, RouteRequest
from .cache import ProviderCache
from .credentials import CredentialMetadataV1, CredentialStore, CredentialStoreError
from .models import ProviderAuditEventV1, ProviderCostEstimateV1
from .policy import ProviderPolicyV1
from .probe import CapabilityProbeService, ProbeMode, ProbeSnapshotV1
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
    project_id: str | None = Field(default=None, max_length=200)
    credential_ref: str | None = Field(default=None, max_length=200)
    capability_id: str = Field(min_length=1, max_length=100)
    model: str | None = Field(default=None, max_length=200)
    input_refs: list[str] = Field(default_factory=list, max_length=10_000)
    parameters: dict[str, object] = Field(default_factory=dict, max_length=128)
    expected_output_schema: str = Field(min_length=1, max_length=200)
    timeout_ms: int = Field(default=120_000, ge=100, le=86_400_000)
    region: str | None = Field(default=None, max_length=64)
    data_classification: Literal["public", "internal", "sensitive", "restricted"] = "sensitive"
    max_cost_minor: int | None = Field(default=None, ge=0)
    allow_failover: bool = True


class ProviderCancelRequest(_ContractModel):
    operation_id: UUID


class ProviderPolicyUpdate(_ContractModel):
    policy: ProviderPolicyV1


class CredentialPutRequest(_ContractModel):
    credential_ref: str
    provider_id: str
    secret: str = Field(min_length=1, max_length=100_000)
    scope: str = Field(min_length=1, max_length=200)


class CredentialSecretRequest(_ContractModel):
    secret: str = Field(min_length=1, max_length=100_000)


@dataclass
class ProviderApiState:
    registry: ProviderRegistry
    adapters: dict[str, ProviderAdapter]
    probe_service: CapabilityProbeService = field(default_factory=CapabilityProbeService)
    policies: dict[tuple[str, str], ProviderPolicyV1] = field(default_factory=dict)
    usage_minor: dict[tuple[str, str], int] = field(default_factory=dict)
    health: dict[tuple[str, str], ProbeSnapshotV1] = field(default_factory=dict)
    audit_events: list[ProviderAuditEventV1] = field(default_factory=list)
    broker: ProviderBroker | None = None
    credential_store: CredentialStore | None = None
    rate_limiter: ProviderRateLimiter = field(default_factory=ProviderRateLimiter)

    def __post_init__(self) -> None:
        if self.broker is None:
            self.broker = ProviderBroker(self.registry, self.adapters, cache=ProviderCache())
        if self.credential_store is None:
            from .credentials import InMemoryCredentialStore

            self.credential_store = InMemoryCredentialStore()


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
    async def list_health(
        response: Response, if_none_match: str | None = Header(default=None)
    ) -> object:
        snapshots = list(state.health.values())
        payload = [_probe_snapshot_json(item) for item in snapshots]
        etag = canonical_sha256({"health": payload})
        response.headers["ETag"] = etag
        if if_none_match == etag:
            return Response(status_code=304, headers={"ETag": etag})
        return payload

    @router.get("/credentials", response_model=list[CredentialMetadataV1])
    async def list_credentials() -> list[CredentialMetadataV1]:
        assert state.credential_store is not None
        return state.credential_store.list_metadata()

    @router.post("/credentials", response_model=CredentialMetadataV1, status_code=201)
    async def put_credential(request: CredentialPutRequest) -> CredentialMetadataV1:
        assert state.credential_store is not None
        try:
            return state.credential_store.put(
                request.credential_ref,
                request.provider_id,
                request.secret,
                request.scope,
            )
        except CredentialStoreError as error:
            raise HTTPException(status_code=409, detail="credential_store_rejected") from error

    @router.post("/credentials/{credential_ref}/rotate", response_model=CredentialMetadataV1)
    async def rotate_credential(
        credential_ref: str, request: CredentialSecretRequest
    ) -> CredentialMetadataV1:
        assert state.credential_store is not None
        try:
            return state.credential_store.rotate(credential_ref, request.secret)
        except CredentialStoreError as error:
            raise HTTPException(status_code=404, detail="credential_not_found") from error

    @router.delete("/credentials/{credential_ref}", response_model=CredentialMetadataV1)
    async def revoke_credential(credential_ref: str) -> CredentialMetadataV1:
        assert state.credential_store is not None
        try:
            return state.credential_store.revoke(credential_ref)
        except CredentialStoreError as error:
            raise HTTPException(status_code=404, detail="credential_not_found") from error

    @router.post("/{provider_id}/invoke")
    async def invoke_provider(
        provider_id: str, request: ProviderInvokeRequest
    ) -> object:
        adapter = state.adapters.get(provider_id)
        descriptor = state.registry.get(provider_id)
        if adapter is None or descriptor is None:
            raise HTTPException(status_code=404, detail="provider_not_found")
        if request.credential_ref:
            decision = state.rate_limiter.consume(
                provider_id,
                request.credential_ref,
                request.capability_id,
            )
            if not decision.allowed:
                raise HTTPException(
                    status_code=429,
                    detail="provider_rate_limited",
                    headers={"Retry-After": str(max(1, ceil(decision.retry_after_seconds)))},
                )
        context = _context(request.tenant_id, "provider.invoke", request.timeout_ms)
        assert state.broker is not None
        try:
            routed = await state.broker.invoke(
                RouteRequest(
                    context=context,
                    kind=descriptor.kind,
                    capability_id=request.capability_id,
                    model=request.model,
                    input_refs=request.input_refs,
                    parameters=request.parameters,
                    expected_output_schema=request.expected_output_schema,
                    candidate_provider_ids=[provider_id],
                    fixed_provider_id=provider_id,
                    region=request.region,
                    data_classification=request.data_classification,
                    max_cost_minor=request.max_cost_minor,
                    allow_failover=request.allow_failover,
                )
            )
            if request.project_id and not routed.cache_hit:
                billed = routed.result.billed_cost or 0
                key = (str(request.tenant_id), request.project_id)
                state.usage_minor[key] = state.usage_minor.get(key, 0) + int(billed)
            _record_audit(
                state,
                ProviderAuditEventV1(
                    event_id=uuid4(),
                    operation_id=context.operation_id,
                    tenant_id=request.tenant_id,
                    project_id=request.project_id,
                    provider_id=provider_id,
                    capability_id=request.capability_id,
                    event_kind="cache_hit" if routed.cache_hit else "invoke",
                    status=routed.result.status,
                    billed_cost_minor=int(routed.result.billed_cost or 0),
                    occurred_at=datetime.now(UTC),
                ),
            )
            return routed.result
        except ProviderBrokerError as error:
            _record_audit(
                state,
                ProviderAuditEventV1(
                    event_id=uuid4(),
                    operation_id=context.operation_id,
                    tenant_id=request.tenant_id,
                    project_id=request.project_id,
                    provider_id=provider_id,
                    capability_id=request.capability_id,
                    event_kind="failure",
                    status="failed",
                    billed_cost_minor=0,
                    occurred_at=datetime.now(UTC),
                    error_code=error.error.code,
                ),
            )
            raise HTTPException(
                status_code=502,
                detail=error.error.model_dump(mode="json"),
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

    @router.get("/audit", response_model=list[ProviderAuditEventV1])
    async def list_audit_events(
        tenant_id: UUID, project_id: str | None = None
    ) -> list[ProviderAuditEventV1]:
        return [
            event
            for event in state.audit_events
            if event.tenant_id == tenant_id
            and (project_id is None or event.project_id == project_id)
        ]

    return router


def _record_audit(state: ProviderApiState, event: ProviderAuditEventV1) -> None:
    state.audit_events.append(event)
    del state.audit_events[:-1000]


def _probe_snapshot_json(snapshot: ProbeSnapshotV1) -> dict[str, object]:
    return {
        "provider_id": snapshot.provider_id,
        "capability_id": snapshot.capability_id,
        "mode": snapshot.mode,
        "health": snapshot.health.model_dump(mode="json"),
        "observed_at": snapshot.observed_at.isoformat().replace("+00:00", "Z"),
        "expires_at": snapshot.expires_at.isoformat().replace("+00:00", "Z"),
        "billed_probe": snapshot.billed_probe,
        "evidence_sha256": snapshot.evidence_sha256,
    }


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
