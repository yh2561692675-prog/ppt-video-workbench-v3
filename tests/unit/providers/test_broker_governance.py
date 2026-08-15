from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from workbench.contracts.p2_platform import BudgetV1, OperationContextV1
from workbench.providers.adapter import DeterministicFakeProvider, FakeProviderBehavior
from workbench.providers.broker import ProviderBroker, ProviderBrokerError, RouteRequest
from workbench.providers.governance import PersistentCostLedger, ProviderGovernance
from workbench.providers.models import ProviderCapabilityV1, ProviderDescriptorV1
from workbench.providers.policy import ProviderPolicyV1
from workbench.providers.registry import ProviderRegistry


def _descriptor(provider_id: str, execution_mode: str) -> ProviderDescriptorV1:
    return ProviderDescriptorV1(
        provider_id=provider_id,
        display_name=provider_id,
        kind="tts",
        adapter_version="1.0.0",
        execution_mode=execution_mode,  # type: ignore[arg-type]
        capabilities=[
            ProviderCapabilityV1(
                capability_id="synthesize.speech",
                modalities=["audio"],
                supports_cost_estimate=True,
            )
        ],
        trust="builtin_signed",
    )


def _request() -> RouteRequest:
    now = datetime.now(UTC)
    context = OperationContextV1(
        operation_id=uuid4(),
        idempotency_key=uuid4(),
        attempt_id=uuid4(),
        tenant_id=uuid4(),
        request_kind="provider.invoke",
        started_at=now,
        budget=BudgetV1(timeout_ms=1000),
    )
    return RouteRequest(
        context=context,
        kind="tts",
        capability_id="synthesize.speech",
        policy=ProviderPolicyV1(allow_remote_https=True, allow_failover=True),
        credential_ref="credential.ref",
        budget_scopes=("operation",),
    )


@pytest.mark.asyncio
async def test_remote_unknown_billing_blocks_automatic_failover(tmp_path: Path) -> None:
    remote = DeterministicFakeProvider(
        _descriptor("a-remote-tts", "remote_https"),
        FakeProviderBehavior(failure_mode="retryable"),
    )
    local = DeterministicFakeProvider(_descriptor("z-local-tts", "in_process_builtin"))
    governance = ProviderGovernance(
        PersistentCostLedger(tmp_path / "ledger.json", {"operation": 100})
    )
    broker = ProviderBroker(
        ProviderRegistry([remote.descriptor, local.descriptor]),
        {"a-remote-tts": remote, "z-local-tts": local},
        governance=governance,
    )
    with pytest.raises(ProviderBrokerError) as raised:
        await broker.invoke(_request())
    assert len(raised.value.attempts) == 1
    assert raised.value.error.failover_allowed is False
    assert governance.ledger.list()[0].status == "unknown"
