from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from workbench.cache.gc import CacheGarbageCollector
from workbench.cache.models import CacheEntry
from workbench.cache.repository import CacheRepository


def _entry(
    key: str,
    path: str,
    *,
    age: int,
    protected: bool = False,
    lease_count: int = 0,
) -> CacheEntry:
    return CacheEntry(
        cache_key=key * 64,
        project_id=uuid4(),
        artifact_hash=key * 64,
        relative_path=path,
        size_bytes=100,
        protected=protected,
        lease_count=lease_count,
        last_accessed_at=datetime.now(UTC) - timedelta(hours=age),
    )


def test_gc_dry_run_and_execution_preserve_protected_and_leased_entries(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    repository = CacheRepository(tmp_path / "cache-index.json")
    entries = [
        _entry("a", "old.bin", age=3),
        _entry("b", "leased.bin", age=2, lease_count=1),
        _entry("c", "protected.bin", age=1, protected=True),
    ]
    for entry in entries:
        (root / entry.relative_path).write_bytes(b"x" * entry.size_bytes)
        repository.put(entry)
    collector = CacheGarbageCollector(
        repository,
        root,
        high_watermark_bytes=250,
        low_watermark_bytes=200,
    )

    preview = collector.collect(dry_run=True)
    executed = collector.collect(dry_run=False)

    assert [item.cache_key for item in preview.candidates] == ["a" * 64]
    assert (root / "old.bin").exists() is False
    assert (root / "leased.bin").is_file()
    assert (root / "protected.bin").is_file()
    assert executed.bytes_reclaimed == 100
    assert repository.get("a" * 64) is None
