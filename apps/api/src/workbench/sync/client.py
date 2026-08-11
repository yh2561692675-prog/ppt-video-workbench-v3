from __future__ import annotations

import json
import os
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
        self,
        message: str,
        *,
        retryable: bool = True,
        conflict_id: str | None = None,
        conflict: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.conflict_id = conflict_id
        self.conflict = conflict


class SyncTransport(Protocol):
    def append_operation(self, operation_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...

    def list_operations(self, cursor: str | None = None) -> dict[str, Any]: ...

    def download_object(self, object_id: str) -> bytes: ...

    def resolve_conflict(
        self, conflict_id: str, resolution: dict[str, Any]
    ) -> dict[str, Any]: ...


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
                "cursor TEXT NOT NULL, applied_at TEXT NOT NULL, "
                "status TEXT NOT NULL DEFAULT 'pending')"
            )
            remote_columns = {
                str(row[1]) for row in db.execute("PRAGMA table_info(remote_operations)")
            }
            if "status" not in remote_columns:
                db.execute(
                    "ALTER TABLE remote_operations ADD COLUMN status TEXT NOT NULL "
                    "DEFAULT 'pending'"
                )
            db.execute(
                "CREATE TABLE IF NOT EXISTS sync_state ("
                "key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS conflicts ("
                "conflict_id TEXT PRIMARY KEY, operation_id TEXT NOT NULL UNIQUE, "
                "details_json TEXT NOT NULL, status TEXT NOT NULL, "
                "resolution_json TEXT, updated_at TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS object_transfers ("
                "object_id TEXT PRIMARY KEY, staging_path TEXT NOT NULL, "
                "total_size INTEGER NOT NULL, received_size INTEGER NOT NULL, "
                "status TEXT NOT NULL, updated_at TEXT NOT NULL)"
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

    def mark_conflict(
        self,
        operation_id: str,
        conflict_id: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        conflict = details or {"conflict_id": conflict_id}
        _assert_sync_payload(conflict, field="conflict")
        with self._lock, self._connect() as db:
            cursor = db.execute(
                "UPDATE outbox SET status='conflict', attempts=attempts+1, cursor=?, "
                "last_error='manual_merge_required', updated_at=? WHERE operation_id=?",
                (conflict_id, _now(), operation_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(operation_id)
            db.execute(
                "INSERT INTO conflicts "
                "(conflict_id, operation_id, details_json, status, updated_at) "
                "VALUES (?, ?, ?, 'open', ?) "
                "ON CONFLICT(conflict_id) DO UPDATE SET "
                "details_json=excluded.details_json, updated_at=excluded.updated_at",
                (
                    conflict_id,
                    operation_id,
                    json.dumps(conflict, ensure_ascii=False, sort_keys=True),
                    _now(),
                ),
            )

    def conflicts(self, *, status: str | None = None) -> list[dict[str, Any]]:
        self._require_enabled()
        if status not in {None, "open", "resolved"}:
            raise ValueError("status must be open, resolved, or None")
        query = "SELECT * FROM conflicts"
        parameters: tuple[object, ...] = ()
        if status is not None:
            query += " WHERE status=?"
            parameters = (status,)
        query += " ORDER BY updated_at, conflict_id"
        with self._connect() as db:
            rows = db.execute(query, parameters).fetchall()
        return [
            {
                "conflict_id": row["conflict_id"],
                "operation_id": row["operation_id"],
                "details": json.loads(row["details_json"]),
                "status": row["status"],
                "resolution": (
                    json.loads(row["resolution_json"]) if row["resolution_json"] else None
                ),
            }
            for row in rows
        ]

    def resolve_conflict(
        self,
        transport: SyncTransport,
        operation_id: str,
        *,
        strategy: str,
        expected_head_revision_id: str,
        reason: str,
        merged_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._require_enabled()
        if strategy not in {"keep_remote", "apply_local", "merged"}:
            raise ValueError("invalid conflict resolution strategy")
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM conflicts WHERE operation_id=? AND status='open'",
                (operation_id,),
            ).fetchone()
        if row is None:
            raise KeyError(operation_id)
        resolution: dict[str, Any] = {
            "expected_head_revision_id": expected_head_revision_id,
            "strategy": strategy,
            "reason": reason,
        }
        if merged_payload is not None:
            resolution["merged_payload"] = merged_payload
        _assert_sync_payload(resolution, field="conflict.resolution")
        result = transport.resolve_conflict(str(row["conflict_id"]), resolution)
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE conflicts SET status='resolved', resolution_json=?, updated_at=? "
                "WHERE operation_id=?",
                (
                    json.dumps(result, ensure_ascii=False, sort_keys=True),
                    _now(),
                    operation_id,
                ),
            )
            db.execute(
                "UPDATE outbox SET status='resolved', last_error=NULL, updated_at=? "
                "WHERE operation_id=?",
                (_now(), operation_id),
            )
        return result

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

    def pending_remote_operations(self, limit: int = 100) -> list[dict[str, Any]]:
        self._require_enabled()
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        with self._connect() as db:
            rows = db.execute(
                "SELECT operation_id, payload_json, cursor FROM remote_operations "
                "WHERE status='pending' ORDER BY applied_at, operation_id LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "operation_id": row["operation_id"],
                "payload": json.loads(row["payload_json"]),
                "cursor": row["cursor"],
            }
            for row in rows
        ]

    def mark_remote_applied(self, operation_id: str) -> None:
        self._require_enabled()
        with self._lock, self._connect() as db:
            db.execute(
                "UPDATE remote_operations SET status='applied' WHERE operation_id=?",
                (operation_id,),
            )
            if db.total_changes == 0:
                raise KeyError(operation_id)

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

    def stage_object_chunk(
        self,
        object_id: str,
        content: bytes,
        staging_root: Path,
        *,
        offset: int,
        total_size: int,
    ) -> Path:
        """Append one resumable chunk and atomically publish only after final hash validation."""

        self._require_enabled()
        digest = object_id.removeprefix("sha256:")
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or offset < 0 or total_size < 0:
            raise ValueError("invalid object transfer declaration")
        staging_root.mkdir(parents=True, exist_ok=True)
        root = staging_root.resolve()
        target = (root / digest).resolve()
        if target.parent != root:
            raise ValueError("invalid object staging path")
        temporary = target.with_suffix(".part")
        current_size = temporary.stat().st_size if temporary.exists() else 0
        if current_size != offset:
            raise ValueError("object transfer offset mismatch")
        if current_size + len(content) > total_size:
            raise ValueError("object transfer exceeds declared size")
        with temporary.open("ab") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        received_size = temporary.stat().st_size
        status = "staged" if received_size == total_size else "partial"
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO object_transfers "
                "(object_id, staging_path, total_size, received_size, status, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(object_id) DO UPDATE SET "
                "total_size=excluded.total_size, received_size=excluded.received_size, "
                "status=excluded.status, updated_at=excluded.updated_at",
                (object_id, digest, total_size, received_size, status, _now()),
            )
        if received_size < total_size:
            return temporary
        if sha256(temporary.read_bytes()).hexdigest() != digest:
            temporary.unlink(missing_ok=True)
            with self._lock, self._connect() as db:
                db.execute(
                    "UPDATE object_transfers SET received_size=0, status='hash_mismatch', "
                    "updated_at=? "
                    "WHERE object_id=?",
                    (_now(), object_id),
                )
            raise ValueError("object hash mismatch")
        temporary.replace(target)
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO inbox VALUES (?, ?, ?, ?)",
                (object_id, digest, object_id, _now()),
            )
            db.execute(
                "UPDATE object_transfers SET status='complete', updated_at=? WHERE object_id=?",
                (_now(), object_id),
            )
        return target

    def begin_full_rebuild(self) -> None:
        """Reset only the remote replica cursor; durable local outbox entries are preserved."""

        self._require_enabled()
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM remote_operations")
            db.execute("DELETE FROM sync_state WHERE key='remote_cursor'")

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
                    self.mark_conflict(operation_id, error.conflict_id, error.conflict)
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
