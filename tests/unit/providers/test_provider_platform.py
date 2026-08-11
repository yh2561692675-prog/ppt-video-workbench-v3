from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from workbench.contracts.p2_platform import BudgetV1, OperationContextV1
from workbench.providers.adapter import DeterministicFakeProvider, FakeProviderBehavior
from workbench.providers.broker import ProviderBroker, ProviderBrokerError, RouteRequest
from workbench.providers.cache import ProviderCache, cache_identity
from workbench.providers.models import ProviderCapabilityV1, ProviderDescriptorV1
from workbench.providers.registry import ProviderRegistry, ProviderRegistryError


def descriptor(provider_id: str, *, kind: str = "tts") -> ProviderDescriptorV1:
    return ProviderDescriptorV1(
        provider_id=provider_id,
        display_name=provider_id,
        kind=kind,
        adapter_version="1.0.0",
        execution_mode="in_process_builtin",
        capabilities=[
            ProviderCapabilityV1(
                capability_id="synthesize.speech",
                modalities=["audio"],
                languages=["zh-CN"],
                supports_cancellation=True,
                supports_cost_estimate=True,
                data_regions=["CN"],
            )
        ],
    )


def context(*, timeout_ms: int = 1000) -> OperationContextV1:
    now = datetime.now(UTC)
    return OperationContextV1(
        operation_id=uuid4(),
        idempotency_key=uuid4(),
        attempt_id=uuid4(),
        tenant_id=uuid4(),
        request_kind="provider.invoke",
        started_at=now,
        deadline_at=now + timedelta(seconds=5),
        budget=BudgetV1(timeout_ms=timeout_ms, max_attempts=3),
    )


def request(ctx: OperationContextV1, **kwargs) -> RouteRequest:
    return RouteRequest(
        context=ctx,
        kind="tts",
        capability_id="synthesize.speech",
        input_refs=["sha256:" + "a" * 64],
        expected_output_schema="audio-v1",
        parameters={"voice.id": "fake"},
        **kwargs,
    )


def test_registry_load_isolates_invalid_descriptors() -> None:
    registry, diagnostics = ProviderRegistry.load(
        [descriptor("fake-a").model_dump(mode="json"), {"provider_id": "bad", "kind": "unknown"}]
    )
    assert registry.get("fake-a") is not None
    assert len(diagnostics) == 1
    with pytest.raises(ProviderRegistryError):
        registry.register(descriptor("fake-a"))


def test_descriptor_rejects_dynamic_execution_mode() -> None:
    with pytest.raises(ValidationError):
        ProviderDescriptorV1(
            provider_id="unsafe",
            display_name="Unsafe",
            kind="tts",
            adapter_version="1.0.0",
            execution_mode="python_import",  # type: ignore[arg-type]
            capabilities=[descriptor("fake").capabilities[0]],
        )


@pytest.mark.asyncio
async def test_broker_failover_preserves_operation_and_changes_attempt() -> None:
    first = DeterministicFakeProvider(
        descriptor("fake-a"), FakeProviderBehavior(failure_mode="retryable")
    )
    second = DeterministicFakeProvider(descriptor("fake-b"))
    registry = ProviderRegistry([first.descriptor, second.descriptor])
    broker = ProviderBroker(registry, {"fake-a": first, "fake-b": second})
    ctx = context()
    result = await broker.invoke(request(ctx))
    assert result.result.provider_id == "fake-b"
    assert result.result.operation_id == ctx.operation_id
    assert len(result.attempts) == 2
    assert result.attempts[0].attempt_id != result.attempts[1].attempt_id


@pytest.mark.asyncio
async def test_fixed_provider_does_not_fail_over() -> None:
    first = DeterministicFakeProvider(
        descriptor("fake-a"), FakeProviderBehavior(failure_mode="retryable")
    )
    second = DeterministicFakeProvider(descriptor("fake-b"))
    broker = ProviderBroker(
        ProviderRegistry([first.descriptor, second.descriptor]), {"fake-a": first, "fake-b": second}
    )
    with pytest.raises(ProviderBrokerError) as raised:
        await broker.invoke(request(context(), fixed_provider_id="fake-a"))
    assert raised.value.error.code == "fake_retryable"
    assert len(raised.value.attempts) == 1


@pytest.mark.asyncio
async def test_idempotency_returns_original_result_without_second_call() -> None:
    fake = DeterministicFakeProvider(descriptor("fake-a"))
    broker = ProviderBroker(ProviderRegistry([fake.descriptor]), {"fake-a": fake})
    ctx = context()
    first = await broker.invoke(request(ctx))
    second = await broker.invoke(request(ctx))
    assert first == second
    assert len(fake.calls) == 1


@pytest.mark.asyncio
async def test_budget_gate_rejects_unknown_cost_before_invoke() -> None:
    fake = DeterministicFakeProvider(
        descriptor("fake-a"), FakeProviderBehavior(failure_mode="unknown_billing")
    )
    broker = ProviderBroker(ProviderRegistry([fake.descriptor]), {"fake-a": fake})
    with pytest.raises(ProviderBrokerError) as raised:
        await broker.invoke(request(context(), max_cost_minor=10))
    assert raised.value.error.code == "provider.cost_unknown"
    assert fake.calls == []


def test_cache_identity_isolated_by_provider_and_tenant() -> None:
    base = dict(
        capability_id="synthesize.speech",
        adapter_version="1.0.0",
        model_resolved="voice-a",
        parameters={"voice.id": "fake"},
        input_fingerprints=["sha256:" + "a" * 64],
        output_schema_version="audio-v1",
    )
    left = cache_identity(provider_id="fake-a", tenant_scope="tenant-a", **base)
    right = cache_identity(provider_id="fake-b", tenant_scope="tenant-a", **base)
    other_tenant = cache_identity(provider_id="fake-a", tenant_scope="tenant-b", **base)
    assert len({left, right, other_tenant}) == 3


def test_cache_identity_invalidates_platform_runtime_and_revision_changes() -> None:
    base = dict(
        provider_id="fake-a",
        capability_id="synthesize.speech",
        adapter_version="1.0.0",
        model_resolved="voice-a",
        parameters={"voice.id": "fake"},
        input_fingerprints=["sha256:" + "a" * 64],
        output_schema_version="audio-v1",
        tenant_scope="tenant-a",
    )
    baseline = cache_identity(
        **base,
        platform_fingerprint="sha256:" + "1" * 64,
        runtime_fingerprint="sha256:" + "2" * 64,
        font_fingerprint="sha256:" + "3" * 64,
        cloud_revision_id="revision-a",
    )
    changed = cache_identity(
        **base,
        platform_fingerprint="sha256:" + "9" * 64,
        runtime_fingerprint="sha256:" + "2" * 64,
        font_fingerprint="sha256:" + "3" * 64,
        cloud_revision_id="revision-a",
    )
    changed_revision = cache_identity(
        **base,
        platform_fingerprint="sha256:" + "1" * 64,
        runtime_fingerprint="sha256:" + "2" * 64,
        font_fingerprint="sha256:" + "3" * 64,
        cloud_revision_id="revision-b",
    )
    assert len({baseline, changed, changed_revision}) == 3


def test_cache_expires_entries() -> None:
    cache = ProviderCache(default_ttl_seconds=1)
    assert cache.get("tenant", "sha256:" + "a" * 64) is None
