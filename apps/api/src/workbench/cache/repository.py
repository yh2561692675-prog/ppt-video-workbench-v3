from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from workbench.cache.models import CacheEntry


class CacheRepository:
    def __init__(self, index_path: Path) -> None:
        self.index_path = index_path
        self._lock = RLock()
        self._entries = self._load()

    def put(self, entry: CacheEntry) -> CacheEntry:
        with self._lock:
            existing = self._entries.get(entry.cache_key)
            selected = existing if existing is not None else entry
            self._entries[entry.cache_key] = selected
            self._persist()
            return selected

    def get(self, cache_key: str, *, touch: bool = True) -> CacheEntry | None:
        with self._lock:
            entry = self._entries.get(cache_key)
            if entry is None:
                return None
            if touch:
                entry = entry.model_copy(update={"last_accessed_at": datetime.now(UTC)})
                self._entries[cache_key] = entry
                self._persist()
            return entry

    def list(self) -> list[CacheEntry]:
        with self._lock:
            return sorted(
                self._entries.values(),
                key=lambda entry: (entry.last_accessed_at, entry.cache_key),
            )

    def remove(self, cache_key: str) -> CacheEntry | None:
        with self._lock:
            removed = self._entries.pop(cache_key, None)
            if removed is not None:
                self._persist()
            return removed

    def set_lease_count(self, cache_key: str, lease_count: int) -> CacheEntry:
        if lease_count < 0:
            raise ValueError("lease count must not be negative")
        with self._lock:
            current = self._entries[cache_key]
            updated = current.model_copy(update={"lease_count": lease_count})
            self._entries[cache_key] = updated
            self._persist()
            return updated

    def _load(self) -> dict[str, CacheEntry]:
        if not self.index_path.is_file():
            return {}
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            entries = [CacheEntry.model_validate(item) for item in payload.get("entries", [])]
        except (OSError, ValueError, json.JSONDecodeError):
            return {}
        return {entry.cache_key: entry for entry in entries}

    def _persist(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.index_path.with_name(f".{self.index_path.name}.tmp")
        payload = {
            "schema_version": "1.0",
            "entries": [entry.model_dump(mode="json") for entry in self.list()],
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.index_path)
