from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from workbench.providers.governance import (
    CostLedgerError,
    PersistentCostLedger,
    ProviderGovernance,
)
from workbench.providers.policy import ProviderPolicyV1


def test_cost_ledger_persists_reservation_and_requires_unknown_reconciliation(
    tmp_path: Path,
) -> None:
    ledger_path = tmp_path / "settings" / "provider-cost-ledger.json"
    operation_id = uuid4()
    ledger = PersistentCostLedger(ledger_path, {"project": 100})
    entry = ledger.reserve(
        operation_id=operation_id,
        provider_id="remote-llm",
        capability_id="complete.text",
        amount_minor=40,
        scopes=("project",),
        price_book_version="2026-08",
    )
    ledger.mark_unknown(entry.reservation_id)
    with pytest.raises(CostLedgerError, match="reconciled"):
        ledger.release(entry.reservation_id)

    restarted = PersistentCostLedger(ledger_path, {"project": 100})
    unknown = restarted.get(entry.reservation_id)
    assert unknown.status == "unknown"
    committed = restarted.commit(entry.reservation_id, 35)
    assert committed.status == "committed"
    assert committed.committed_cost_minor == 35


def test_governance_reserves_once_and_blocks_budget_overrun(tmp_path: Path) -> None:
    governance = ProviderGovernance(
        PersistentCostLedger(tmp_path / "ledger.json", {"project": 50})
    )
    first = governance.authorize(
        operation_id=uuid4(),
        provider_id="remote-tts",
        credential_ref="cred.ref",
        capability_id="synthesize.speech",
        estimated_cost_minor=40,
        scopes=("project",),
        price_book_version="2026-08",
    )
    assert first.allowed is True
    second = governance.authorize(
        operation_id=uuid4(),
        provider_id="remote-tts",
        credential_ref="cred.ref",
        capability_id="synthesize.speech",
        estimated_cost_minor=20,
        scopes=("project",),
        price_book_version="2026-08",
    )
    assert second.allowed is False
    assert second.reason.startswith("budget_exceeded")


def test_unknown_billing_never_allows_failover(tmp_path: Path) -> None:
    governance = ProviderGovernance(PersistentCostLedger(tmp_path / "ledger.json"))
    policy = ProviderPolicyV1(allow_failover=True)
    assert governance.may_failover(
        policy=policy,
        error_code="provider.timeout",
        error_retryable=True,
        billed_state="unknown",
    ) is False
    assert governance.may_failover(
        policy=policy,
        error_code="provider.timeout",
        error_retryable=True,
        billed_state="known",
    ) is True
