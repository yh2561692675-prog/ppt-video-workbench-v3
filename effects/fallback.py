from __future__ import annotations

from collections.abc import Sequence

from .schema import EffectPlanV2, FallbackPlan
from .validator import ValidationIssue


def fallback_effect_plan(plan: EffectPlanV2, issues: Sequence[ValidationIssue]) -> EffectPlanV2:
    reason = "; ".join(issue.code for issue in issues) or "validation fallback"
    return plan.model_copy(
        update={
            "effects": [],
            "fallback": FallbackPlan(template="SafeSlide", reason=reason),
        }
    )
