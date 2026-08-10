from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class PresenterPlacement:
    action: str
    rect: dict[str, float] | None
    effects_unchanged: bool = True


def resolve_presenter_placement(
    *, presenter_rect: Mapping[str, float], caption_safe_area: Mapping[str, float], aspect_ratio: str
) -> PresenterPlacement:
    """Keep presenter outside captions; aspect ratio only selects deterministic candidates."""
    current = _normalise(presenter_rect)
    caption = _normalise(caption_safe_area)
    if not _overlaps(current, caption):
        return PresenterPlacement("keep", current)

    candidates = [
        {"x": 0.04, "y": 0.04, "width": current["width"], "height": current["height"]},
        {"x": 0.72, "y": 0.04, "width": current["width"], "height": current["height"]},
        {"x": 0.04, "y": 0.72, "width": current["width"], "height": current["height"]},
    ]
    for candidate in candidates:
        if not _overlaps(candidate, caption) and _within(candidate):
            return PresenterPlacement("move", candidate)

    shrunk = {**current, "width": current["width"] * 0.75, "height": current["height"] * 0.75}
    if not _overlaps(shrunk, caption) and _within(shrunk):
        return PresenterPlacement("shrink", shrunk)
    return PresenterPlacement("hide", None)


def _normalise(rect: Mapping[str, float]) -> dict[str, float]:
    return {key: float(rect[key]) for key in ("x", "y", "width", "height")}


def _overlaps(left: Mapping[str, float], right: Mapping[str, float]) -> bool:
    return left["x"] < right["x"] + right["width"] and right["x"] < left["x"] + left["width"] and left["y"] < right["y"] + right["height"] and right["y"] < left["y"] + left["height"]


def _within(rect: Mapping[str, float]) -> bool:
    return 0 <= rect["x"] and 0 <= rect["y"] and rect["x"] + rect["width"] <= 1 and rect["y"] + rect["height"] <= 1
