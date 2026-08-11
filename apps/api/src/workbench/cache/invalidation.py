from __future__ import annotations

from workbench.cache.contracts import (
    CacheDomain,
    CacheInvalidationEvent,
    StaleReason,
)


def subtitle_invalidation(
    source_key: str,
    *,
    render_mode: str,
    previous_hash: str | None,
    current_hash: str,
    start_us: int | None = None,
    end_us: int | None = None,
) -> CacheInvalidationEvent:
    domains = {
        "soft": (CacheDomain.SUBTITLE_SOFT,),
        "burn_in": (CacheDomain.SUBTITLE_BURN_IN,),
        "both": (CacheDomain.SUBTITLE_SOFT, CacheDomain.SUBTITLE_BURN_IN),
        "none": (),
    }.get(render_mode)
    if domains is None:
        raise ValueError("unsupported subtitle render mode")
    return CacheInvalidationEvent(
        source_kind="subtitle_revision",
        source_key=source_key,
        previous_hash=previous_hash,
        current_hash=current_hash,
        reason=StaleReason.SOURCE_REVISION_CHANGED,
        domains=domains,
        start_us=start_us,
        end_us=end_us,
    )


def audio_cut_invalidation(
    source_key: str,
    *,
    previous_hash: str | None,
    current_hash: str,
    start_us: int | None = None,
    end_us: int | None = None,
) -> CacheInvalidationEvent:
    return CacheInvalidationEvent(
        source_kind="continuity_revision",
        source_key=source_key,
        previous_hash=previous_hash,
        current_hash=current_hash,
        reason=StaleReason.SOURCE_REVISION_CHANGED,
        domains=(CacheDomain.AUDIO,),
        start_us=start_us,
        end_us=end_us,
    )


def layout_invalidation(
    source_key: str,
    *,
    previous_hash: str | None,
    current_hash: str,
) -> CacheInvalidationEvent:
    return CacheInvalidationEvent(
        source_kind="timeline_revision",
        source_key=source_key,
        previous_hash=previous_hash,
        current_hash=current_hash,
        reason=StaleReason.LAYOUT_CHANGED,
        domains=(
            CacheDomain.LAYOUT,
            CacheDomain.VIDEO_ONLY,
            CacheDomain.OVERLAY,
            CacheDomain.TRANSITION,
            CacheDomain.SUBTITLE_BURN_IN,
            CacheDomain.FINAL,
        ),
    )
