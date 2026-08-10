from __future__ import annotations


def test_p09_effect_planner_uses_safe_fallback_for_empty_content() -> None:
    from workbench.business_modules.p09_effects.runner import plan_effect

    result = plan_effect({"page_id": "p1", "duration_ms": 3000, "title": "", "text": ""})

    assert result["plan"]["template"] == "SafeSlide"
    assert result["status"] == "fallback"
