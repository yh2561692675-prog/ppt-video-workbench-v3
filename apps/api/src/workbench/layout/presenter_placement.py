from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from workbench.domain.occupancy import NormalizedRect, PageOccupancyMap, overlap_ratio
from workbench.domain.presenter import PresenterSegment

Aspect = Literal["16:9", "9:16"]
VisibleLayout = Literal["top_left", "top_right", "bottom_left", "bottom_right"]


class PlacementContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PresenterPlacement(PlacementContract):
    layout: Literal["top_left", "top_right", "bottom_left", "bottom_right", "hidden"]
    rect: NormalizedRect | None = None
    width_ratio: float = Field(ge=0, le=1)
    score: float
    reasons: list[str] = Field(default_factory=list)


class PresenterCue(PlacementContract):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    reason: str = "speech"
    preferred_layout: VisibleLayout | None = None


def choose_placement(
    occupancy: PageOccupancyMap,
    *,
    aspect: Aspect,
    previous_layout: VisibleLayout | None = None,
    preferred_layout: VisibleLayout | None = None,
) -> PresenterPlacement:
    widths = (0.22, 0.18) if aspect == "16:9" else (0.48, 0.40, 0.38)
    best: PresenterPlacement | None = None
    for width in widths:
        for layout in ("top_left", "top_right", "bottom_left", "bottom_right"):
            rect = _candidate_rect(layout, width, aspect)
            critical_overlap = overlap_ratio(rect, occupancy.critical)
            if critical_overlap > 0:
                continue
            content_overlap = overlap_ratio(rect, occupancy.content)
            caption_overlap = overlap_ratio(rect, occupancy.captions)
            movement_penalty = 0.08 if previous_layout and previous_layout != layout else 0.0
            preference_bonus = 0.12 if preferred_layout == layout else 0.0
            if occupancy.preferred_region == layout:
                preference_bonus += 0.08
            score = 1.0 - content_overlap * 0.55 - caption_overlap * 0.85 - movement_penalty
            score += preference_bonus + (0.22 - width if aspect == "16:9" else 0.48 - width) * 0.1
            candidate = PresenterPlacement(
                layout=layout,
                rect=rect,
                width_ratio=width,
                score=round(score, 4),
                reasons=[
                    f"content_overlap:{content_overlap:.4f}",
                    f"caption_overlap:{caption_overlap:.4f}",
                ],
            )
            if best is None or (candidate.score, -_layout_order(layout)) > (
                best.score,
                -_layout_order(best.layout),
            ):
                best = candidate
        if best is not None and best.score >= 0.75:
            break
    return best or PresenterPlacement(
        layout="hidden", width_ratio=0, score=0, reasons=["no_safe_region"]
    )


def plan_presenter_segments(
    occupancy: PageOccupancyMap,
    cues: list[PresenterCue],
    *,
    aspect: Aspect,
) -> list[PresenterSegment]:
    segments: list[PresenterSegment] = []
    previous_layout: VisibleLayout | None = None
    for cue in sorted(cues, key=lambda item: item.start_ms):
        placement = choose_placement(
            occupancy,
            aspect=aspect,
            previous_layout=previous_layout,
            preferred_layout=cue.preferred_layout,
        )
        segments.append(
            PresenterSegment(
                start_ms=cue.start_ms,
                end_ms=cue.end_ms,
                layout=placement.layout,
                width_ratio=placement.width_ratio,
            )
        )
        if placement.layout != "hidden":
            previous_layout = placement.layout
    return segments


def _candidate_rect(layout: VisibleLayout, width: float, aspect: Aspect) -> NormalizedRect:
    margin = 0.04
    height = width if aspect == "16:9" else width * 0.31640625
    x = margin if layout.endswith("left") else 1 - margin - width
    y = margin if layout.startswith("top") else 1 - margin - height
    return NormalizedRect(x=x, y=y, width=width, height=height)


def _layout_order(layout: str) -> int:
    return ("top_left", "top_right", "bottom_left", "bottom_right", "hidden").index(layout)
