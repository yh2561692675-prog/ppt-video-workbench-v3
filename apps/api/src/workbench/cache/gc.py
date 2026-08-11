from __future__ import annotations

from pathlib import Path, PurePosixPath

from workbench.cache.models import CacheGcCandidate, CacheGcResult
from workbench.cache.repository import CacheRepository


class CacheGcError(ValueError):
    pass


class CacheGarbageCollector:
    def __init__(
        self,
        repository: CacheRepository,
        artifact_root: Path,
        *,
        high_watermark_bytes: int,
        low_watermark_bytes: int,
    ) -> None:
        if low_watermark_bytes < 0 or high_watermark_bytes < low_watermark_bytes:
            raise ValueError("cache watermarks are invalid")
        self.repository = repository
        self.artifact_root = artifact_root.resolve()
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
        candidates: list[CacheGcCandidate] = []
        projected = bytes_before
        for entry in entries:
            if projected <= self.low_watermark_bytes:
                break
            if entry.protected or not entry.rebuildable or entry.lease_count > 0:
                continue
            candidate = CacheGcCandidate(
                cache_key=entry.cache_key,
                relative_path=entry.relative_path,
                size_bytes=entry.size_bytes,
                reason="least-recently-used rebuildable artifact",
            )
            candidates.append(candidate)
            projected -= entry.size_bytes
            if not dry_run:
                path = self._resolve(entry.relative_path)
                if path.is_file():
                    path.unlink()
                self.repository.remove(entry.cache_key)
        return CacheGcResult(
            dry_run=dry_run,
            bytes_before=bytes_before,
            bytes_reclaimed=bytes_before - projected,
            candidates=candidates,
        )

    def _resolve(self, relative_path: str) -> Path:
        relative = PurePosixPath(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise CacheGcError("cache artifact path must be relative")
        path = self.artifact_root.joinpath(*relative.parts).resolve(strict=False)
        try:
            path.relative_to(self.artifact_root)
        except ValueError as error:
            raise CacheGcError("cache artifact escapes artifact root") from error
        return path
