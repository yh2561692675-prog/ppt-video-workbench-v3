from __future__ import annotations

from effects.presenter import resolve_presenter_placement


def test_presenter_moves_out_of_caption_safe_area_without_changing_effects() -> None:
    placement = resolve_presenter_placement(
        presenter_rect={"x": 0.72, "y": 0.72, "width": 0.24, "height": 0.2},
        caption_safe_area={"x": 0.05, "y": 0.78, "width": 0.9, "height": 0.17},
        aspect_ratio="16:9",
    )

    assert placement.action in {"move", "shrink", "hide"}
    assert placement.rect is None or placement.rect["y"] + placement.rect["height"] <= 0.78
    assert placement.effects_unchanged is True
