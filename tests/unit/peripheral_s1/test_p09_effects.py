from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from peripheral_contracts import JobEnvelope


def test_p09_effect_planner_uses_safe_fallback_for_empty_content() -> None:
    from workbench.business_modules.p09_effects.runner import plan_effect

    result = plan_effect({"page_id": "p1", "duration_ms": 3000, "title": "", "text": ""})

    assert result["plan"]["template"] == "SafeSlide"
    assert result["status"] == "fallback"


def test_p09_reduced_motion_changes_cache_identity_without_invalidating_plan(tmp_path) -> None:
    from workbench.business_modules.p09_effects.runner import _handle

    common = {
        "page_id": str(uuid4()),
        "duration_ms": 3000,
        "title": "Metric 42",
        "text": "42",
        "project_revision": 1,
    }

    def run(reduced_motion: bool):
        return _handle(
            JobEnvelope(
                schema_version="1.0",
                job_id=uuid4(),
                project_id=uuid4(),
                job_type="effect.plan",
                requested_by="test",
                idempotency_key=uuid4().hex,
                parameters={**common, "reduced_motion": reduced_motion},
                created_at=datetime.now(UTC),
            ),
            tmp_path,
        ).business_result

    normal = run(False)
    reduced = run(True)
    assert normal.cache_key != reduced.cache_key
    assert normal.payload["record"]["plan_hash"] == reduced.payload["record"]["plan_hash"]
