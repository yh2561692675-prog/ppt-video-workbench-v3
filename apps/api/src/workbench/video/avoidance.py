from __future__ import annotations

from typing import Literal
from uuid import UUID

from .models import SubtitlePlacement, TextRect

CANVAS_WIDTH = 1_920
CANVAS_HEIGHT = 1_080
SAFE_MARGIN = 96


def choose_subtitle_placement(
    occupied: list[TextRect],
    *,
    page_id: UUID,
    subtitle_width: float,
    subtitle_height: float,
) -> SubtitlePlacement:
    x = (CANVAS_WIDTH - subtitle_width) / 2
    candidates: list[tuple[Literal["bottom", "top", "middle"], TextRect]] = [
        (
            "bottom",
            TextRect(
                x=x,
                y=CANVAS_HEIGHT - SAFE_MARGIN - subtitle_height,
                width=subtitle_width,
                height=subtitle_height,
            ),
        ),
        ("top", TextRect(x=x, y=SAFE_MARGIN, width=subtitle_width, height=subtitle_height)),
        (
            "middle",
            TextRect(
                x=x,
                y=(CANVAS_HEIGHT - subtitle_height) / 2,
                width=subtitle_width,
                height=subtitle_height,
            ),
        ),
    ]
    for position, rect in candidates:
        if not any(_overlaps(rect, item) for item in occupied):
            return SubtitlePlacement(page_id=page_id, position=position, rect=rect)
    return SubtitlePlacement(
        page_id=page_id,
        position="fallback-panel",
        rect=candidates[0][1],
        panel=True,
        reason="候选字幕位置均与页面文字冲突，使用半透明底板",
    )


def _overlaps(left: TextRect, right: TextRect) -> bool:
    return not (
        left.x + left.width <= right.x
        or right.x + right.width <= left.x
        or left.y + left.height <= right.y
        or right.y + right.height <= left.y
    )
