from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import RLock
from typing import Any, Protocol


@dataclass(frozen=True)
class SyncClientState:
    pending: int
    retryable: int
    conflict: int
    accepted: int
    failed: int
    last_cursor: str | None
    remote_operations: int = 0


class SyncTransportError(RuntimeError):
    def __init__(
        self, message: str, *, retryable: bool = True, conflict_id: str | None = None
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.conflict_id = conflict_id


class SyncTransport(Protocol):
    def append_operation(self, operation_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    def list_operations(self, cursor: str | None = None) -> dict[str, Any]: ...

    def download_object(self, object_id: str) -> bytes: ...


@dataclass(frozen=True)
class SyncBatchResult:
    accepted: int
    retryable: int
    conflict: int
    failed: int


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
            db.execute(
                "CREATE TABLE IF NOT EXISTS remote_operations ("
                "operation_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, "
                "cursor TEXT NOT NULL, applied_at TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS sync_state ("
                "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )

    def enqueue(self, operation_id: str, payload: dict[str, Any]) -> bool:
        self._require_enabled()
        _assert_sync_payload(payload)
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
            row = db.execute("SELECT value FROM sync_state WHERE key='remote_cursor'").fetchone()
            if row is None:
                row = db.execute(
                    "SELECT cursor FROM outbox WHERE status='accepted' "
                    "ORDER BY updated_at DESC LIMIT 1"
                ).fetchone()
            remote_count = int(
                db.execute("SELECT count(*) FROM remote_operations").fetchone()[0]
            )
        return SyncClientState(
            pending=int(counts.get("pending", 0)),
            retryable=int(counts.get("retryable", 0)),
            conflict=int(counts.get("conflict", 0)),
            accepted=int(counts.get("accepted", 0)),
            failed=int(counts.get("failed", 0)),
            last_cursor=str(row[0]) if row else None,
            remote_operations=remote_count,
        )

    def pull(self, transport: SyncTransport, *, limit: int = 100) -> list[dict[str, Any]]:
        """Durably stage a remote operation page before a merge service applies it."""

        self._require_enabled()
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        if not hasattr(transport, "list_operations"):
            raise SyncTransportError(
                "sync transport does not support pulling operations", retryable=False
            )
        with self._connect() as db:
            row = db.execute("SELECT value FROM sync_state WHERE key='remote_cursor'").fetchone()
        cursor = str(row[0]) if row else None
        response = transport.list_operations(cursor)
        items = response.get("items", []) if isinstance(response, dict) else []
        if not isinstance(items, list):
            raise SyncTransportError("cloud sync returned invalid operation page", retryable=False)
        accepted: list[dict[str, Any]] = []
        next_cursor = cursor
        with self._lock, self._connect() as db:
            for item in items[:limit]:
                if not isinstance(item, dict):
                    raise SyncTransportError(
                        "cloud sync returned invalid operation", retryable=False
                    )
                operation_id = str(item.get("operation_id", ""))
                if not operation_id:
                    raise SyncTransportError("cloud sync operation has no id", retryable=False)
                _assert_sync_payload(item)
                server_cursor = str(item.get("server_revision_id") or operation_id)
                db.execute(
                    "INSERT OR IGNORE INTO remote_operations "
                    "(operation_id, payload_json, cursor, applied_at) VALUES (?, ?, ?, ?)",
                    (
                        operation_id,
                        json.dumps(item, ensure_ascii=False, sort_keys=True),
                        server_cursor,
                        _now(),
                    ),
                )
                accepted.append(item)
                next_cursor = operation_id
            if next_cursor is not None and next_cursor != cursor:
                db.execute(
                    "INSERT INTO sync_state(key, value) VALUES('remote_cursor', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (next_cursor,),
                )
        return accepted

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
                (object_id, expected, object_id, _now()),
            )
        return target

    def flush(self, transport: SyncTransport, *, limit: int = 20) -> SyncBatchResult:
        """Submit an outbox batch without deleting unacknowledged operations."""

        self._require_enabled()
        counts = {"accepted": 0, "retryable": 0, "conflict": 0, "failed": 0}
        for item in self.next_batch(limit):
            operation_id = str(item["operation_id"])
            try:
                result = transport.append_operation(operation_id, item["payload"])
            except SyncTransportError as error:
                if error.conflict_id:
                    self.mark_conflict(operation_id, error.conflict_id)
                    counts["conflict"] += 1
                elif error.retryable:
                    self.mark_retryable(operation_id, str(error))
                    counts["retryable"] += 1
                else:
                    self.mark_failed(operation_id, str(error))
                    counts["failed"] += 1
                continue
            status = str(result.get("status", "failed"))
            if status == "accepted":
                self.mark_accepted(operation_id, str(result.get("cursor", operation_id)))
                counts["accepted"] += 1
            elif status == "conflict":
                self.mark_conflict(operation_id, str(result.get("conflict_id", "conflict")))
                counts["conflict"] += 1
            elif status == "retryable":
                self.mark_retryable(operation_id, str(result.get("error", "retryable")))
                counts["retryable"] += 1
            else:
                self.mark_failed(operation_id, str(result.get("error", "sync failed")))
                counts["failed"] += 1
        return SyncBatchResult(**counts)

    def download_and_stage(
        self, transport: SyncTransport, object_id: str, staging_root: Path
    ) -> Path:
        """Download into staging and publish only after content-address validation."""

        return self.stage_object(object_id, transport.download_object(object_id), staging_root)

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise RuntimeError("cloud sync is disabled")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _assert_sync_payload(value: object, *, field: str = "payload") -> None:
    """Keep the local outbox portable and free of credential-bearing values."""

    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).lower()
            if any(
                marker in normalized
                for marker in ("api_key", "authorization", "password", "secret")
            ):
                raise ValueError("sensitive sync field rejected")
            _assert_sync_payload(item, field=f"{field}.{key}")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _assert_sync_payload(item, field=f"{field}[{index}]")
        return
    if not isinstance(value, str):
        return
    normalized_field = field.lower()
    if normalized_field.endswith(("path", "_path", "file", "_file", "directory", "_dir")):
        if value.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:[\\/]", value):
            raise ValueError("absolute sync path rejected")
        if value.startswith(("../", "..\\")) or value == "..":
            raise ValueError("sync path escape rejected")
