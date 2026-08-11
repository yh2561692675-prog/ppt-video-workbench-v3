from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any


@dataclass(frozen=True)
class SyncClientState:
    pending: int
    retryable: int
    conflict: int
    accepted: int
    failed: int
    last_cursor: str | None


class SyncClient:
    """SQLite WAL outbox/inbox with acknowledged operations never discarded."""

    def __init__(self, db_path: Path, *, enabled: bool) -> None:
        self.enabled = enabled
        self.db_path = db_path
        self._lock = RLock()
        if enabled:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._init_db()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, check_same_thread=False)
        db.row_factory = sqlite3.Row
        return db

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.execute(
                "CREATE TABLE IF NOT EXISTS outbox ("
                "operation_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, "
                "status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, "
                "last_error TEXT, cursor TEXT, updated_at TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS inbox ("
                "object_id TEXT PRIMARY KEY, staging_path TEXT NOT NULL, "
                "content_sha256 TEXT NOT NULL, applied_at TEXT NOT NULL)"
            )

    def enqueue(self, operation_id: str, payload: dict[str, Any]) -> bool:
        self._require_enabled()
        with self._lock, self._connect() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO outbox(operation_id, payload_json, status, updated_at) "
                "VALUES (?, ?, 'pending', ?)",
                (operation_id, json.dumps(payload, ensure_ascii=False, sort_keys=True), _now()),
            )
        return cursor.rowcount == 1

    def next_batch(self, limit: int = 20) -> list[dict[str, Any]]:
        self._require_enabled()
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        with self._connect() as db:
            rows = db.execute(
                "SELECT operation_id, payload_json, attempts FROM outbox "
                "WHERE status IN ('pending', 'retryable') "
                "ORDER BY updated_at, operation_id LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "operation_id": row["operation_id"],
                "payload": json.loads(row["payload_json"]),
                "attempts": row["attempts"],
            }
            for row in rows
        ]

    def mark_accepted(self, operation_id: str, cursor: str) -> None:
        self._set_status(operation_id, "accepted", cursor=cursor, error=None)

    def mark_retryable(self, operation_id: str, error: str) -> None:
        self._set_status(operation_id, "retryable", cursor=None, error=error[:500])

    def mark_failed(self, operation_id: str, error: str) -> None:
        self._set_status(operation_id, "failed", cursor=None, error=error[:500])

    def mark_conflict(self, operation_id: str, conflict_id: str) -> None:
        self._set_status(
            operation_id, "conflict", cursor=conflict_id, error="manual_merge_required"
        )

    def _set_status(
        self, operation_id: str, status: str, *, cursor: str | None, error: str | None
    ) -> None:
        self._require_enabled()
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE outbox SET status=?, attempts=attempts+1, cursor=?, "
                "last_error=?, updated_at=? WHERE operation_id=?",
                (status, cursor, error, _now(), operation_id),
            )
            if db.total_changes == 0:
                raise KeyError(operation_id)

    def state(self) -> SyncClientState:
        self._require_enabled()
        with self._connect() as db:
            counts = {
                str(row["status"]): int(row["count"])
                for row in db.execute(
                    "SELECT status, count(*) AS count FROM outbox GROUP BY status"
                )
            }
            row = db.execute(
                "SELECT cursor FROM outbox WHERE status='accepted' ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
        return SyncClientState(
            pending=int(counts.get("pending", 0)),
            retryable=int(counts.get("retryable", 0)),
            conflict=int(counts.get("conflict", 0)),
            accepted=int(counts.get("accepted", 0)),
            failed=int(counts.get("failed", 0)),
            last_cursor=str(row[0]) if row else None,
        )

    def stage_object(self, object_id: str, content: bytes, staging_root: Path) -> Path:
        self._require_enabled()
        expected = object_id.removeprefix("sha256:")
        actual = sha256(content).hexdigest()
        if not expected or expected != actual:
            raise ValueError("object hash mismatch")
        target = (staging_root / expected).resolve()
        staging_root.resolve()
        if target.parent != staging_root.resolve():
            raise ValueError("invalid object staging path")
        staging_root.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".part")
        temporary.write_bytes(content)
        temporary.replace(target)
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO inbox VALUES (?, ?, ?, ?)",
                (object_id, str(target), object_id, _now()),
            )
        return target

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise RuntimeError("cloud sync is disabled")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
