from __future__ import annotations

import hashlib
import json

import pytest
from pydantic import ValidationError

from effects.schema import EffectPlanV2, migrate_effect_plan

V1_FIXTURE = {
    "schema_version": "1.0",
    "page_id": "page-1",
    "page_type": "content",
    "duration_ms": 5000,
    "effects": [
        {"type": "fade_in", "start_ms": 0, "end_ms": 500},
    ],
    "manual_lock": False,
}


def _legacy_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_v1_plan_migrates_without_visual_behavior_change() -> None:
    migrated = migrate_effect_plan(V1_FIXTURE)

    assert migrated.schema_version == "2.0"
    assert migrated.rhythm_profile == "steady"
    assert migrated.legacy_payload_hash == _legacy_hash(V1_FIXTURE)
    assert migrated.migration_version == "v1-to-v2"
    assert migrated.effects[0].start_ms == 0
    assert migrated.effects[0].end_ms == 500


def test_v2_contract_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        EffectPlanV2.model_validate(
            {
                "page_id": "page-1",
                "page_type": "content",
                "duration_ms": 5000,
                "unknown": True,
            }
        )
