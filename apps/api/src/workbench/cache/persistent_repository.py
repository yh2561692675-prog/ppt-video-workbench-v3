from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import RowMapping

from workbench.cache.contracts import (
    CacheDependency,
    CacheEntryState,
    CacheInvalidationEvent,
    StaleReason,
    normalize_dependencies,
)
from workbench.cache.models import CacheLookupResult, PersistentCacheEntry
from workbench.storage.workspace_db import (
    WorkspaceDatabase,
    cache_dependencies,
    cache_entries,
)


class PersistentCacheRepository:
    def __init__(self, database: WorkspaceDatabase, artifact_root: Path) -> None:
        self.database = database
        self.artifact_root = artifact_root.resolve()

    def put(self, entry: PersistentCacheEntry) -> PersistentCacheEntry:
        normalized = entry.model_copy(
            update={"dependencies": normalize_dependencies(list(entry.dependencies))}
        )
        values = self._entry_values(normalized)
        with self.database.engine.begin() as connection:
            connection.execute(
                sqlite_insert(cache_entries)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[cache_entries.c.cache_key],
                    set_={
                        **values,
                        "revision": cache_entries.c.revision + 1,
                    },
                )
            )
            connection.execute(
                delete(cache_dependencies).where(
                    cache_dependencies.c.cache_key == normalized.cache_key
                )
            )
            if normalized.dependencies:
                connection.execute(
                    cache_dependencies.insert(),
                    [
                        {
                            "dependency_key": dependency.dependency_key,
                            "cache_key": normalized.cache_key,
                            "domain": dependency.domain.value,
                            "node_key": dependency.node_key,
                            "upstream_kind": dependency.upstream_kind,
                            "upstream_key": dependency.upstream_key,
                            "upstream_hash": dependency.upstream_hash,
                            "start_us": dependency.start_us,
                            "end_us": dependency.end_us,
                            "artifact_refs_json": _canonical_json(
                                [
                                    artifact.model_dump(mode="json")
                                    for artifact in dependency.artifact_refs
                                ]
                            ),
                        }
                        for dependency in normalized.dependencies
                    ],
                )
        return self.get(normalized.cache_key) or normalized

    def get(self, cache_key: str) -> PersistentCacheEntry | None:
        with self.database.connect() as connection:
            row = connection.execute(
                select(cache_entries).where(cache_entries.c.cache_key == cache_key)
            ).mappings().one_or_none()
            if row is None:
                return None
            dependency_rows = connection.execute(
                select(cache_dependencies)
                .where(cache_dependencies.c.cache_key == cache_key)
                .order_by(cache_dependencies.c.dependency_key)
            ).mappings()
            dependencies = tuple(_dependency_from_row(item) for item in dependency_rows)
        return _entry_from_row(row, dependencies)

    def lookup(self, cache_key: str, *, runtime_fingerprint: str) -> CacheLookupResult:
        entry = self.get(cache_key)
        if entry is None:
            return CacheLookupResult(hit=False, reason="missing")
        if entry.state is not CacheEntryState.READY:
            return CacheLookupResult(hit=False, reason=entry.state.value, entry=entry)
        if entry.runtime_fingerprint != runtime_fingerprint:
            self._mark_state(cache_key, CacheEntryState.STALE, StaleReason.RUNTIME_INCOMPATIBLE)
            return CacheLookupResult(hit=False, reason="runtime_incompatible")
        if entry.license_status in {"expired", "blocked"}:
            self._mark_state(cache_key, CacheEntryState.STALE, StaleReason.LICENSE_INVALID)
            return CacheLookupResult(hit=False, reason="license_invalid")
        if not self._acquire_read_lease(cache_key):
            return CacheLookupResult(hit=False, reason="concurrent_invalidation")
        try:
            try:
                path = self.resolve_artifact(entry.relative_path)
                valid_manifest = (
                    _sha256_json(entry.artifact_manifest) == entry.artifact_manifest_hash
                )
                valid_file = (
                    path.is_file()
                    and path.stat().st_size == entry.size_bytes
                    and _sha256_file(path) == entry.artifact_hash
                )
            except (OSError, ValueError):
                valid_manifest = valid_file = False
            if not valid_manifest or not valid_file:
                self._mark_state(
                    cache_key, CacheEntryState.CORRUPTED, StaleReason.ARTIFACT_MISMATCH
                )
                return CacheLookupResult(hit=False, reason="corrupted")
            with self.database.engine.begin() as connection:
                connection.execute(
                    update(cache_entries)
                    .where(
                        cache_entries.c.cache_key == cache_key,
                        cache_entries.c.state == CacheEntryState.READY.value,
                    )
                    .values(last_accessed_at=datetime.now(UTC).isoformat())
                )
            return CacheLookupResult(hit=True, reason="hit", entry=entry)
        finally:
            self._release_read_lease(cache_key)

    def reverse_dependencies(
        self, event: CacheInvalidationEvent
    ) -> tuple[tuple[str, CacheDependency], ...]:
        criteria = [
            cache_dependencies.c.upstream_kind == event.source_kind,
            cache_dependencies.c.upstream_key == event.source_key,
        ]
        if event.domains:
            criteria.append(
                cache_dependencies.c.domain.in_([domain.value for domain in event.domains])
            )
        with self.database.connect() as connection:
            rows = connection.execute(
                select(cache_dependencies).where(*criteria).order_by(cache_dependencies.c.cache_key)
            ).mappings()
            candidates = [
                (str(row["cache_key"]), _dependency_from_row(row)) for row in rows
            ]
        return tuple(
            item
            for item in candidates
            if _ranges_overlap(item[1], event.start_us, event.end_us)
        )

    def invalidate(self, event: CacheInvalidationEvent) -> tuple[str, ...]:
        keys = sorted({cache_key for cache_key, _ in self.reverse_dependencies(event)})
        if not keys:
            return ()
        with self.database.engine.begin() as connection:
            connection.execute(
                update(cache_entries)
                .where(cache_entries.c.cache_key.in_(keys))
                .values(
                    state=CacheEntryState.STALE.value,
                    stale_reason=event.reason.value,
                    revision=cache_entries.c.revision + 1,
                )
            )
        return tuple(keys)

    def set_lease_count(self, cache_key: str, count: int) -> None:
        if count < 0:
            raise ValueError("cache lease count must not be negative")
        with self.database.engine.begin() as connection:
            connection.execute(
                update(cache_entries)
                .where(cache_entries.c.cache_key == cache_key)
                .values(lease_count=count, revision=cache_entries.c.revision + 1)
            )

    def list(self, project_id: UUID | None = None) -> list[PersistentCacheEntry]:
        statement = select(cache_entries)
        if project_id is not None:
            statement = statement.where(cache_entries.c.project_id == str(project_id))
        statement = statement.order_by(
            cache_entries.c.last_accessed_at, cache_entries.c.cache_key
        )
        with self.database.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        entries: list[PersistentCacheEntry] = []
        for row in rows:
            entry = self.get(str(row["cache_key"]))
            if entry is not None:
                entries.append(entry)
        return entries

    def reserve_gc(self, cache_key: str, expected_revision: int) -> bool:
        with self.database.engine.begin() as connection:
            result = connection.execute(
                update(cache_entries)
                .where(
                    cache_entries.c.cache_key == cache_key,
                    cache_entries.c.revision == expected_revision,
                    cache_entries.c.lease_count == 0,
                    cache_entries.c.protected.is_(False),
                )
                .values(
                    state=CacheEntryState.QUARANTINED.value,
                    revision=cache_entries.c.revision + 1,
                )
            )
        return result.rowcount == 1

    def remove_quarantined(self, cache_key: str) -> bool:
        with self.database.engine.begin() as connection:
            result = connection.execute(
                delete(cache_entries).where(
                    cache_entries.c.cache_key == cache_key,
                    cache_entries.c.state == CacheEntryState.QUARANTINED.value,
                    cache_entries.c.lease_count == 0,
                )
            )
            if result.rowcount == 1:
                connection.execute(
                    delete(cache_dependencies).where(
                        cache_dependencies.c.cache_key == cache_key
                    )
                )
        return result.rowcount == 1

    def _mark_state(
        self, cache_key: str, state: CacheEntryState, reason: StaleReason
    ) -> None:
        with self.database.engine.begin() as connection:
            connection.execute(
                update(cache_entries)
                .where(cache_entries.c.cache_key == cache_key)
                .values(
                    state=state.value,
                    stale_reason=reason.value,
                    revision=cache_entries.c.revision + 1,
                )
            )

    def resolve_artifact(self, relative_path: str) -> Path:
        relative = PurePosixPath(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("cache artifact path must be contained")
        resolved = self.artifact_root.joinpath(*relative.parts).resolve(strict=False)
        try:
            resolved.relative_to(self.artifact_root)
        except ValueError as error:
            raise ValueError("cache artifact escapes root") from error
        return resolved

    def _acquire_read_lease(self, cache_key: str) -> bool:
        with self.database.engine.begin() as connection:
            result = connection.execute(
                update(cache_entries)
                .where(
                    cache_entries.c.cache_key == cache_key,
                    cache_entries.c.state == CacheEntryState.READY.value,
                )
                .values(lease_count=cache_entries.c.lease_count + 1)
            )
        return result.rowcount == 1

    def _release_read_lease(self, cache_key: str) -> None:
        with self.database.engine.begin() as connection:
            connection.execute(
                update(cache_entries)
                .where(
                    cache_entries.c.cache_key == cache_key,
                    cache_entries.c.lease_count > 0,
                )
                .values(lease_count=cache_entries.c.lease_count - 1)
            )

    @staticmethod
    def _entry_values(entry: PersistentCacheEntry) -> dict[str, object]:
        return {
            "cache_key": entry.cache_key,
            "project_id": str(entry.project_id),
            "domain": entry.domain.value,
            "node_key": entry.node_key,
            "state": entry.state.value,
            "artifact_manifest_json": _canonical_json(entry.artifact_manifest),
            "artifact_manifest_hash": entry.artifact_manifest_hash,
            "relative_path": entry.relative_path,
            "artifact_hash": entry.artifact_hash,
            "size_bytes": entry.size_bytes,
            "runtime_fingerprint": entry.runtime_fingerprint,
            "license_status": entry.license_status,
            "rebuildable": entry.rebuildable,
            "protected": entry.protected,
            "lease_count": entry.lease_count,
            "stale_reason": entry.stale_reason,
            "created_at": entry.created_at.isoformat(),
            "last_accessed_at": entry.last_accessed_at.isoformat(),
            "revision": entry.revision,
        }


def _entry_from_row(
    row: RowMapping, dependencies: tuple[CacheDependency, ...]
) -> PersistentCacheEntry:
    values = dict(row)
    return PersistentCacheEntry(
        cache_key=values["cache_key"],
        project_id=UUID(values["project_id"]),
        domain=values["domain"],
        node_key=values["node_key"],
        state=values["state"],
        artifact_manifest=json.loads(values["artifact_manifest_json"]),
        artifact_manifest_hash=values["artifact_manifest_hash"],
        relative_path=values["relative_path"],
        artifact_hash=values["artifact_hash"],
        size_bytes=values["size_bytes"],
        runtime_fingerprint=values["runtime_fingerprint"],
        license_status=values["license_status"],
        dependencies=dependencies,
        rebuildable=bool(values["rebuildable"]),
        protected=bool(values["protected"]),
        lease_count=values["lease_count"],
        stale_reason=values["stale_reason"],
        created_at=datetime.fromisoformat(values["created_at"]),
        last_accessed_at=datetime.fromisoformat(values["last_accessed_at"]),
        revision=values["revision"],
    )


def _dependency_from_row(row: RowMapping) -> CacheDependency:
    values = dict(row)
    return CacheDependency(
        domain=values["domain"],
        node_key=values["node_key"],
        upstream_kind=values["upstream_kind"],
        upstream_key=values["upstream_key"],
        upstream_hash=values["upstream_hash"],
        start_us=values["start_us"],
        end_us=values["end_us"],
        artifact_refs=json.loads(values["artifact_refs_json"]),
    )


def _ranges_overlap(
    dependency: CacheDependency, start_us: int | None, end_us: int | None
) -> bool:
    if start_us is None or end_us is None:
        return True
    if dependency.start_us is None or dependency.end_us is None:
        return True
    return dependency.start_us < end_us and dependency.end_us > start_us


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
