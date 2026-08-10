from uuid import UUID

from workbench.video.avoidance import TextRect, choose_subtitle_placement


def test_prefers_bottom_subtitle_position_inside_safe_zone() -> None:
    placement = choose_subtitle_placement(
        [TextRect(x=100, y=100, width=600, height=240)],
        page_id=UUID(int=1),
        subtitle_width=900,
        subtitle_height=90,
    )

    assert placement.position == "bottom"
    assert placement.panel is False
    assert placement.rect.x >= 96
    assert placement.rect.y + placement.rect.height <= 1_080 - 96


def test_uses_translucent_panel_and_reports_reason_when_candidates_collide() -> None:
    occupied = [
        TextRect(x=0, y=0, width=1_920, height=360),
        TextRect(x=0, y=360, width=1_920, height=360),
        TextRect(x=0, y=720, width=1_920, height=360),
    ]

    placement = choose_subtitle_placement(
        occupied,
        page_id=UUID(int=2),
        subtitle_width=900,
        subtitle_height=90,
    )

    assert placement.position == "fallback-panel"
    assert placement.panel is True
    assert "候选字幕位置均与页面文字冲突" in placement.reason
