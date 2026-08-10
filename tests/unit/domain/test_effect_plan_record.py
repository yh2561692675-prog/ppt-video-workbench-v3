from __future__ import annotations

from datetime import UTC, datetime

import pytest
from workbench.domain.effects import EffectPlanRecord, EffectProjectPolicy, validate_record_hash
from workbench.effects.schema import EffectPlanV2


def _plan() -> EffectPlanV2:
    return EffectPlanV2(
        page_id="page-1",
        page_type="content",
        duration_ms=1_000,
    )


def test_effect_plan_record_rejects_a_client_supplied_wrong_hash() -> None:
    record = EffectPlanRecord(
        revision=1,
        plan=_plan(),
        plan_hash="0" * 64,
        input_fingerprint="1" * 64,
        source="automatic",
        status="ready",
        updated_at=datetime.now(UTC),
    )

    with pytest.raises(ValueError, match="plan_hash"):
        validate_record_hash(record)


def test_effect_policy_defaults_to_horizontal_generation() -> None:
    assert EffectProjectPolicy().aspect_ratio == "16:9"
