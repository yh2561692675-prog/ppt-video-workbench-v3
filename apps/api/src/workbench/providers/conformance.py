"""Network-free adapter conformance harness."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from workbench.contracts.p2_platform import BudgetV1, OperationContextV1

from .adapter import ProviderAdapter
from .models import ProviderInvocationV1
from .v2 import AdapterConformanceResultV1


async def run_adapter_conformance(adapter: ProviderAdapter) -> AdapterConformanceResultV1:
    """Exercise the stable adapter boundary with a deterministic fake operation.

    The harness never calls a network transport itself. A real adapter may still
    be configured to use a sandbox; callers should pass a fake or a sandbox
    adapter in CI and set ``fake_provider`` accordingly in their evidence.
    """

    now = datetime.now(UTC)
    context = OperationContextV1(
        operation_id=uuid4(),
        idempotency_key=uuid4(),
        attempt_id=uuid4(),
        tenant_id=uuid4(),
        request_kind="provider.conformance",
        started_at=now,
        budget=BudgetV1(timeout_ms=5_000, max_attempts=1),
    )
    invocation = ProviderInvocationV1(
        operation=context,
        provider_id=adapter.descriptor.provider_id,
        capability_id=adapter.descriptor.capabilities[0].capability_id,
        model=adapter.descriptor.capabilities[0].models[0]
        if adapter.descriptor.capabilities[0].models
        else None,
        input_refs=["fixture:input"],
        expected_output_schema="provider-output-v1",
    )
    checks: dict[str, str] = {}
    errors: list[str] = []
    try:
        health = await asyncio.wait_for(adapter.probe(invocation), timeout=5)
        checks["probe"] = "pass" if health.status in {"available", "degraded"} else "fail"
    except BaseException:
        checks["probe"] = "fail"
        errors.append("probe_failed")
    try:
        estimate = await asyncio.wait_for(adapter.estimate(invocation), timeout=5)
        checks["estimate"] = "pass" if estimate.currency and estimate.unit else "fail"
    except BaseException:
        checks["estimate"] = "fail"
        errors.append("estimate_failed")
    try:
        result = await asyncio.wait_for(adapter.invoke(invocation), timeout=5)
        checks["invoke"] = "pass" if result.status in {"succeeded", "degraded"} else "fail"
    except BaseException:
        checks["invoke"] = "fail"
        errors.append("invoke_failed")
    try:
        await asyncio.wait_for(adapter.cancel(context.operation_id), timeout=5)
        checks["cancel"] = "pass"
    except BaseException:
        checks["cancel"] = "fail"
        errors.append("cancel_failed")

    status: Literal["pass", "fail", "degraded"] = "pass" if not errors else "fail"
    return AdapterConformanceResultV1(
        adapter_id=adapter.descriptor.provider_id,
        descriptor_fingerprint="sha256:" + "0" * 64,
        status=status,
        checks=checks,  # type: ignore[arg-type]
        error_codes=errors,
    )
