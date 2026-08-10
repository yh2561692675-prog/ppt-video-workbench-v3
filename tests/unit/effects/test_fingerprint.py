from workbench.effects.fingerprint import calculate_input_fingerprint
from workbench.effects.planner import EffectPlanningInput


def test_input_fingerprint_ignores_local_paths_and_is_stable() -> None:
    base = EffectPlanningInput(
        page_id="page-1",
        page_type="content",
        duration_ms=2_000,
        title="Title",
        text="Body",
        source_path="C:/one/page.png",
    )
    changed_path = base.model_copy(update={"source_path": "D:/other/page.png"})

    assert calculate_input_fingerprint(base) == calculate_input_fingerprint(changed_path)
