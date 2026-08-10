from __future__ import annotations

import pytest
from pydantic import ValidationError
from workbench.effects.schema import EffectPlanV2


def _visual_defaults() -> dict[str, object]:
    return {
        "page_id": "page-1",
        "page_type": "content",
        "duration_ms": 5_000,
        "cues": [],
        "effects": [],
    }


def test_plan_requires_explicit_template_and_matching_payload() -> None:
    plan = EffectPlanV2.model_validate(
        {
            **_visual_defaults(),
            "template": "ProgressiveReveal",
            "template_payload": {"kind": "progressive_reveal", "items": ["A", "B"]},
        }
    )

    assert plan.template == "ProgressiveReveal"
    assert plan.template_payload.kind == "progressive_reveal"

    with pytest.raises(ValidationError):
        EffectPlanV2.model_validate(
            {
                **_visual_defaults(),
                "template": "StatCounter",
                "template_payload": {"kind": "progressive_reveal", "items": ["A"]},
            }
        )


def test_safe_slide_is_valid_default_for_legacy_v2_payload() -> None:
    plan = EffectPlanV2.model_validate(_visual_defaults())

    assert plan.template == "SafeSlide"
    assert plan.template_payload.kind == "safe_slide"


def test_progressive_reveal_rejects_more_than_six_items() -> None:
    with pytest.raises(ValidationError):
        EffectPlanV2.model_validate(
            {
                **_visual_defaults(),
                "template": "ProgressiveReveal",
                "template_payload": {
                    "kind": "progressive_reveal",
                    "items": ["1", "2", "3", "4", "5", "6", "7"],
                },
            }
        )
