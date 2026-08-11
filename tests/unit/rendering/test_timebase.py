from __future__ import annotations

import json
from pathlib import Path

from workbench.rendering.timebase import duration_to_frames, us_range_to_frames


def test_timebase_fixture_matches_python_boundaries() -> None:
    root = Path(__file__).parents[3]
    fixture = json.loads(
        (root / "tests" / "fixtures" / "rendergraph-v2" / "timebase.json").read_text(
            encoding="utf-8"
        )
    )
    fps = fixture["fps"]["num"] / fixture["fps"]["den"]
    for case in fixture["cases"]:
        frames = us_range_to_frames(case["start_us"], case["end_us"], round(fps))
        assert frames.start == case["start_frame"]
        assert frames.end == case["end_frame_exclusive"]


def test_timebase_fixture_covers_common_integer_frame_rates() -> None:
    root = Path(__file__).parents[3]
    fixture = json.loads(
        (root / "tests" / "fixtures" / "rendergraph-v2" / "timebase.json").read_text(
            encoding="utf-8"
        )
    )
    for case in fixture["fps_matrix"]:
        assert duration_to_frames(case["duration_us"], case["fps"]) == case["duration_frames"]
        frames = us_range_to_frames(case["start_us"], case["end_us"], case["fps"])
        assert frames.start == case["start_frame"]
        assert frames.end == case["end_frame_exclusive"]
