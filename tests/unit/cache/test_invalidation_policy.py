from __future__ import annotations

from workbench.cache.contracts import CacheDomain
from workbench.cache.invalidation import (
    audio_cut_invalidation,
    layout_invalidation,
    subtitle_invalidation,
)


def test_soft_subtitle_does_not_invalidate_video_only() -> None:
    event = subtitle_invalidation(
        "document",
        render_mode="soft",
        previous_hash="a" * 64,
        current_hash="b" * 64,
    )
    assert event.domains == (CacheDomain.SUBTITLE_SOFT,)
    assert CacheDomain.VIDEO_ONLY not in event.domains


def test_j_or_l_cut_only_invalidates_audio_domain() -> None:
    event = audio_cut_invalidation(
        "boundary-1",
        previous_hash="a" * 64,
        current_hash="b" * 64,
        start_us=1_000_000,
        end_us=2_000_000,
    )
    assert event.domains == (CacheDomain.AUDIO,)


def test_layout_change_invalidates_every_layout_sensitive_domain() -> None:
    event = layout_invalidation(
        "canvas",
        previous_hash="a" * 64,
        current_hash="b" * 64,
    )
    assert {
        CacheDomain.LAYOUT,
        CacheDomain.VIDEO_ONLY,
        CacheDomain.OVERLAY,
        CacheDomain.TRANSITION,
        CacheDomain.SUBTITLE_BURN_IN,
        CacheDomain.FINAL,
    } == set(event.domains)
