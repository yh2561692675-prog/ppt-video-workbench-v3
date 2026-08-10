from __future__ import annotations

import pytest

from effects.fallback import fallback_effect_plan
from effects.schema import EffectPlanV2
from effects.validator import validate_effect_plan


def invalid_plan(issue: str) -> dict[str, object]:
    base: dict[str, object] = {"duration_ms": 5000, "manual_lock": True}
    if issue == "two_main_cameras":
        base["camera_count"] = 2
    elif issue == "caption_overlap":
        base["caption_rect"] = {"x": 0, "y": 0.8, "width": 0.8, "height": 0.15}
        base["occupied_rects"] = [{"x": 0.1, "y": 0.82, "width": 0.4, "height": 0.1}]
    elif issue == "cue_before_speech":
        base["speech_start_ms"] = 1000
        base["cues"] = [{"start_ms": 500, "end_ms": 900}]
    elif issue == "transition_too_long":
        base["transition_duration_ms"] = 700
    elif issue == "infinite_loop":
        base["effects"] = [{"type": "background_breath", "loop": True}]
    return base


@pytest.mark.parametrize(
    "issue",
    [
        "two_main_cameras",
        "caption_overlap",
        "cue_before_speech",
        "transition_too_long",
        "infinite_loop",
    ],
)
def test_invalid_plan_is_rejected(issue: str) -> None:
    report = validate_effect_plan(invalid_plan(issue))

    assert report.blocking is True
    assert report.issues


def test_fallback_preserves_manual_lock() -> None:
    plan = EffectPlanV2(page_id="page-1", page_type="content", duration_ms=5000, manual_lock=True)

    fallback = fallback_effect_plan(
        plan, validate_effect_plan(invalid_plan("infinite_loop")).issues
    )

    assert fallback.manual_lock is True
    assert fallback.fallback.template == "SafeSlide"
