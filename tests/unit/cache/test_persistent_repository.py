from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from time import perf_counter
from uuid import UUID, uuid4

from workbench.cache.contracts import (
    CacheDependency,
    CacheDomain,
    CacheInvalidationEvent,
    StaleReason,
)
from workbench.cache.models import PersistentCacheEntry
from workbench.cache.persistent_gc import PersistentCacheGarbageCollector
from workbench.cache.persistent_repository import PersistentCacheRepository
from workbench.storage.workspace_db import WorkspaceDatabase


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _manifest_hash(value: dict[str, object]) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return _digest(encoded)


def _entry(
    root: Path,
    project_id: UUID,
    key: str,
    domain: CacheDomain,
    dependencies: list[CacheDependency],
) -> PersistentCacheEntry:
    contents = f"artifact-{key}".encode()
    relative = f"artifacts/{key}.bin"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)
    manifest: dict[str, object] = {"relative_path": relative, "size": len(contents)}
    return PersistentCacheEntry(
        cache_key=key * 64 if len(key) == 1 else key,
        project_id=project_id,
        domain=domain,
        node_key=f"{domain.value}:{key}",
        artifact_manifest=manifest,
        artifact_manifest_hash=_manifest_hash(manifest),
        relative_path=relative,
        artifact_hash=_digest(contents),
        size_bytes=len(contents),
        runtime_fingerprint="runtime-v1",
        license_status="confirmed",
        dependencies=tuple(dependencies),
    )


def _dependency(
    domain: CacheDomain,
    key: str,
    *,
    start_us: int = 0,
    end_us: int = 1_000_000,
) -> CacheDependency:
    return CacheDependency(
        domain=domain,
        node_key=f"{domain.value}:{key}",
        upstream_kind="source_revision",
        upstream_key=key,
        upstream_hash="f" * 64,
        start_us=start_us,
        end_us=end_us,
    )


def test_lookup_validates_runtime_manifest_file_and_marks_corruption(tmp_path: Path) -> None:
    database = WorkspaceDatabase(tmp_path / "workspace.db")
    database.initialize()
    repository = PersistentCacheRepository(database, tmp_path)
    project_id = uuid4()
    entry = _entry(
        tmp_path,
        project_id,
        "a",
        CacheDomain.VIDEO_ONLY,
        [_dependency(CacheDomain.VIDEO_ONLY, "slide")],
    )
    repository.put(entry)

    assert repository.lookup(entry.cache_key, runtime_fingerprint="runtime-v1").hit
    assert not repository.lookup(entry.cache_key, runtime_fingerprint="runtime-v2").hit

    replacement = entry.model_copy(update={"cache_key": "b" * 64})
    repository.put(replacement)
    (tmp_path / replacement.relative_path).write_bytes(b"corrupt")
    result = repository.lookup(replacement.cache_key, runtime_fingerprint="runtime-v1")
    assert not result.hit
    assert result.reason == "corrupted"
    assert repository.get(replacement.cache_key).state.value == "corrupted"  # type: ignore[union-attr]


def test_selective_invalidation_respects_domain_source_and_time_range(tmp_path: Path) -> None:
    database = WorkspaceDatabase(tmp_path / "workspace.db")
    database.initialize()
    repository = PersistentCacheRepository(database, tmp_path)
    project_id = uuid4()
    soft = _entry(
        tmp_path,
        project_id,
        "c",
        CacheDomain.SUBTITLE_SOFT,
        [_dependency(CacheDomain.SUBTITLE_SOFT, "subtitle")],
    )
    video = _entry(
        tmp_path,
        project_id,
        "d",
        CacheDomain.VIDEO_ONLY,
        [_dependency(CacheDomain.VIDEO_ONLY, "slide")],
    )
    overlay = _entry(
        tmp_path,
        project_id,
        "e",
        CacheDomain.OVERLAY,
        [_dependency(CacheDomain.OVERLAY, "asset-a", start_us=2_000_000, end_us=3_000_000)],
    )
    for entry in (soft, video, overlay):
        repository.put(entry)

    invalidated = repository.invalidate(
        CacheInvalidationEvent(
            source_kind="source_revision",
            source_key="subtitle",
            reason=StaleReason.SOURCE_REVISION_CHANGED,
            domains=(CacheDomain.SUBTITLE_SOFT,),
        )
    )
    assert invalidated == (soft.cache_key,)
    assert repository.get(video.cache_key).state.value == "ready"  # type: ignore[union-attr]
    assert (tmp_path / soft.relative_path).is_file()

    outside = repository.invalidate(
        CacheInvalidationEvent(
            source_kind="source_revision",
            source_key="asset-a",
            reason=StaleReason.ASSET_REVISION_CHANGED,
            start_us=0,
            end_us=1_000_000,
        )
    )
    assert outside == ()


def test_persistent_gc_quarantines_before_delete_and_preserves_leases(tmp_path: Path) -> None:
    database = WorkspaceDatabase(tmp_path / "workspace.db")
    database.initialize()
    repository = PersistentCacheRepository(database, tmp_path)
    project_id = uuid4()
    stale = _entry(
        tmp_path,
        project_id,
        "f",
        CacheDomain.VIDEO_ONLY,
        [_dependency(CacheDomain.VIDEO_ONLY, "stale")],
    )
    leased = _entry(
        tmp_path,
        project_id,
        "1",
        CacheDomain.VIDEO_ONLY,
        [_dependency(CacheDomain.VIDEO_ONLY, "leased")],
    )
    repository.put(stale)
    repository.put(leased)
    repository.invalidate(
        CacheInvalidationEvent(
            source_kind="source_revision",
            source_key="stale",
            reason=StaleReason.SOURCE_REVISION_CHANGED,
        )
    )
    repository.set_lease_count(leased.cache_key, 1)
    collector = PersistentCacheGarbageCollector(
        repository, high_watermark_bytes=1, low_watermark_bytes=0
    )

    dry_run = collector.collect(dry_run=True)
    executed = collector.collect(dry_run=False)

    assert [item.cache_key for item in dry_run.candidates] == [stale.cache_key]
    assert executed.bytes_reclaimed == stale.size_bytes
    assert repository.get(stale.cache_key) is None
    assert (tmp_path / stale.relative_path).exists() is False
    assert (tmp_path / leased.relative_path).is_file()


def test_reverse_dependency_query_handles_one_thousand_nodes(tmp_path: Path) -> None:
    database = WorkspaceDatabase(tmp_path / "workspace.db")
    database.initialize()
    repository = PersistentCacheRepository(database, tmp_path)
    dependencies = [
        _dependency(CacheDomain.VIDEO_ONLY, f"source-{index}") for index in range(1_000)
    ]
    entry = _entry(tmp_path, uuid4(), "9", CacheDomain.VIDEO_ONLY, dependencies)
    repository.put(entry)

    started = perf_counter()
    matches = repository.reverse_dependencies(
        CacheInvalidationEvent(
            source_kind="source_revision",
            source_key="source-777",
            reason=StaleReason.SOURCE_REVISION_CHANGED,
        )
    )
    elapsed = perf_counter() - started

    assert len(matches) == 1
    assert matches[0][0] == entry.cache_key
    assert elapsed < 1.0


def test_randomized_reverse_query_has_no_missing_or_unrelated_results(tmp_path: Path) -> None:
    database = WorkspaceDatabase(tmp_path / "workspace.db")
    database.initialize()
    repository = PersistentCacheRepository(database, tmp_path)
    generator = random.Random(20260811)
    domains = [CacheDomain.VIDEO_ONLY, CacheDomain.AUDIO, CacheDomain.OVERLAY]
    expected: set[str] = set()
    target_domain = CacheDomain.OVERLAY
    for index in range(40):
        domain = generator.choice(domains)
        source_key = f"source-{generator.randrange(6)}"
        start_us = generator.randrange(5) * 1_000_000
        end_us = start_us + 1_000_000
        cache_key = _digest(f"cache-{index}".encode())
        entry = _entry(
            tmp_path,
            uuid4(),
            cache_key,
            domain,
            [_dependency(domain, source_key, start_us=start_us, end_us=end_us)],
        )
        repository.put(entry)
        if (
            domain is target_domain
            and source_key == "source-3"
            and start_us < 3_000_000
            and end_us > 2_000_000
        ):
            expected.add(entry.cache_key)

    matches = repository.reverse_dependencies(
        CacheInvalidationEvent(
            source_kind="source_revision",
            source_key="source-3",
            reason=StaleReason.SOURCE_REVISION_CHANGED,
            domains=(target_domain,),
            start_us=2_000_000,
            end_us=3_000_000,
        )
    )

    assert {cache_key for cache_key, _ in matches} == expected
