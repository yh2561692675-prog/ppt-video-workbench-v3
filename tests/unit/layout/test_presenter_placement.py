import json
from pathlib import Path

from workbench.domain.occupancy import PageOccupancyMap, overlap_ratio
from workbench.layout.presenter_placement import (
    PresenterCue,
    choose_placement,
    plan_presenter_segments,
)

ROOT = Path(__file__).resolve().parents[3]
CASES = json.loads(
    (ROOT / "tests/fixtures/presenter/occupancy-cases.json").read_text(encoding="utf-8")
)


def test_bottom_right_is_rejected_when_chart_label_is_occupied() -> None:
    occupancy = PageOccupancyMap.model_validate(CASES["bottom_right_chart"])
    plan = choose_placement(occupancy, aspect="16:9", preferred_layout="bottom_right")
    assert plan.layout != "bottom_right"
    assert plan.rect is not None
    assert overlap_ratio(plan.rect, occupancy.critical) == 0


def test_no_safe_region_hides_presenter_instead_of_returning_illegal_rect() -> None:
    occupancy = PageOccupancyMap.model_validate(CASES["all_corners_blocked"])
    plan = choose_placement(occupancy, aspect="9:16")
    assert plan.layout == "hidden"
    assert plan.rect is None
    assert plan.width_ratio == 0


def test_aspect_ratio_widths_follow_presenter_policy() -> None:
    empty = PageOccupancyMap()
    landscape = choose_placement(empty, aspect="16:9")
    portrait = choose_placement(empty, aspect="9:16")
    assert 0.18 <= landscape.width_ratio <= 0.25
    assert 0.38 <= portrait.width_ratio <= 0.55


def test_hidden_segments_do_not_change_cue_timing() -> None:
    occupancy = PageOccupancyMap.model_validate(CASES["all_corners_blocked"])
    cue = PresenterCue(start_ms=500, end_ms=1_500)
    segment = plan_presenter_segments(occupancy, [cue], aspect="16:9")[0]
    assert segment.layout == "hidden"
    assert (segment.start_ms, segment.end_ms) == (500, 1_500)
