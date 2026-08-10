from __future__ import annotations

from workbench.effects.planner import EffectPlanner, EffectPlanningInput


def test_planner_is_deterministic_for_same_page_input() -> None:
    planner = EffectPlanner()
    input_data = EffectPlanningInput(
        page_id="page-1",
        page_type="content",
        duration_ms=3_000,
        title="航天任务",
        text="第一阶段\n第二阶段",
        cue_texts=["第一阶段", "第二阶段"],
    )

    first = planner.plan(input_data)
    second = planner.plan(input_data)

    assert first.plan_hash == second.plan_hash
    assert first.input_fingerprint == second.input_fingerprint
    assert first.plan == second.plan


def test_locked_changed_input_becomes_stale_without_overwriting_plan() -> None:
    planner = EffectPlanner()
    original_input = EffectPlanningInput(
        page_id="page-1", page_type="content", duration_ms=1_000, text="原文"
    )
    existing = planner.plan(original_input).model_copy(update={"locked": True})
    changed_input = original_input.model_copy(update={"text": "新文"})

    result = planner.reconcile(changed_input, existing)

    assert result.plan_hash == existing.plan_hash
    assert result.status == "stale"


def test_empty_content_uses_explicit_safe_slide_fallback() -> None:
    result = EffectPlanner().plan(
        EffectPlanningInput(page_id="page-1", page_type="content", duration_ms=1_000)
    )

    assert result.status == "fallback"
    assert result.source == "fallback"
    assert result.plan.template == "SafeSlide"
