from __future__ import annotations

from workbench.cache.models import CacheGcCandidate, CacheGcResult
from workbench.cache.persistent_repository import PersistentCacheRepository


class PersistentCacheGarbageCollector:
    def __init__(
        self,
        repository: PersistentCacheRepository,
        *,
        high_watermark_bytes: int,
        low_watermark_bytes: int,
    ) -> None:
        if low_watermark_bytes < 0 or high_watermark_bytes < low_watermark_bytes:
            raise ValueError("cache watermarks are invalid")
        self.repository = repository
        self.high_watermark_bytes = high_watermark_bytes
        self.low_watermark_bytes = low_watermark_bytes

    def collect(self, *, dry_run: bool = True) -> CacheGcResult:
        entries = self.repository.list()
        bytes_before = sum(entry.size_bytes for entry in entries)
        if bytes_before <= self.high_watermark_bytes:
            return CacheGcResult(
                dry_run=dry_run,
                bytes_before=bytes_before,
                bytes_reclaimed=0,
                candidates=[],
            )
        eligible = sorted(
            (
                entry
                for entry in entries
                if entry.rebuildable
                and not entry.protected
                and entry.lease_count == 0
            ),
            key=lambda entry: (
                0 if entry.state.value in {"stale", "corrupted"} else 1,
                entry.last_accessed_at,
                entry.cache_key,
            ),
        )
        candidates: list[CacheGcCandidate] = []
        projected = bytes_before
        reclaimed = 0
        for entry in eligible:
            if projected <= self.low_watermark_bytes:
                break
            candidate = CacheGcCandidate(
                cache_key=entry.cache_key,
                relative_path=entry.relative_path,
                size_bytes=entry.size_bytes,
                reason=f"{entry.state.value} rebuildable artifact",
            )
            candidates.append(candidate)
            projected -= entry.size_bytes
            if dry_run or not self.repository.reserve_gc(entry.cache_key, entry.revision):
                continue
            path = self.repository.resolve_artifact(entry.relative_path)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                continue
            if self.repository.remove_quarantined(entry.cache_key):
                reclaimed += entry.size_bytes
        return CacheGcResult(
            dry_run=dry_run,
            bytes_before=bytes_before,
            bytes_reclaimed=(bytes_before - projected) if dry_run else reclaimed,
            candidates=candidates,
        )
