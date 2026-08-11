from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from workbench.sync import SyncClient, SyncTransportError


def test_disabled_sync_does_not_create_database(tmp_path: Path) -> None:
    path = tmp_path / ".sync" / "outbox.db"
    client = SyncClient(path, enabled=False)
    assert not path.exists()
    with pytest.raises(RuntimeError):
        client.state()


def test_outbox_ack_retry_and_staging_are_restart_safe(tmp_path: Path) -> None:
    path = tmp_path / ".sync" / "outbox.db"
    client = SyncClient(path, enabled=True)
    operation_id = str(uuid4())
    assert client.enqueue(operation_id, {"kind": "page.insert"}) is True
    assert client.enqueue(operation_id, {"kind": "duplicate"}) is False
    assert client.next_batch()[0]["operation_id"] == operation_id
    client.mark_retryable(operation_id, "offline")
    assert client.state().retryable == 1
    client.mark_conflict(operation_id, "conflict-1")
    assert client.state().conflict == 1
    client.mark_accepted(operation_id, "cursor-1")
    assert client.state().accepted == 1
    content = b"asset"
    object_id = "sha256:" + sha256(content).hexdigest()
    staged = client.stage_object(object_id, content, tmp_path / "staging")
    assert staged.read_bytes() == content
    restarted = SyncClient(path, enabled=True)
    assert restarted.state().last_cursor == "cursor-1"
    with pytest.raises(ValueError):
        restarted.stage_object("sha256:" + "0" * 64, b"tampered", tmp_path / "staging")


def test_sync_payload_rejects_secrets_and_stores_logical_object_keys(tmp_path: Path) -> None:
    client = SyncClient(tmp_path / ".sync" / "outbox.db", enabled=True)
    with pytest.raises(ValueError, match="sensitive"):
        client.enqueue(str(uuid4()), {"api_key": "secret"})
    content = b"asset"
    object_id = "sha256:" + sha256(content).hexdigest()
    client.stage_object(object_id, content, tmp_path / "staging")
    import sqlite3

    with sqlite3.connect(tmp_path / ".sync" / "outbox.db") as db:
        stored = db.execute("SELECT staging_path FROM inbox").fetchone()[0]
    assert stored == object_id.removeprefix("sha256:")
    assert str(tmp_path) not in stored


def test_sync_flush_preserves_retry_and_conflict_states(tmp_path: Path) -> None:
    client = SyncClient(tmp_path / ".sync" / "outbox.db", enabled=True)
    accepted_id, retry_id, conflict_id = (str(uuid4()) for _ in range(3))
    client.enqueue(accepted_id, {"kind": "page.insert"})
    client.enqueue(retry_id, {"kind": "page.move"})
    client.enqueue(conflict_id, {"kind": "page.replace"})

    class Transport:
        def append_operation(
            self, operation_id: str, payload: dict[str, object]
        ) -> dict[str, object]:
            if operation_id == accepted_id:
                return {"status": "accepted", "cursor": "cursor-1"}
            if operation_id == retry_id:
                raise SyncTransportError("offline", retryable=True)
            raise SyncTransportError("stale base", retryable=False, conflict_id="conflict-1")

        def download_object(self, object_id: str) -> bytes:
            return b"asset"

    result = client.flush(Transport())
    assert result.accepted == 1
    assert result.retryable == 1
    assert result.conflict == 1
    assert client.state().last_cursor == "cursor-1"
