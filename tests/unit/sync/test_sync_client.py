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


def test_sync_client_pulls_operations_atomically_and_resumes(tmp_path: Path) -> None:
    client = SyncClient(tmp_path / "sync.db", enabled=True)

    class Transport:
        pages = [
            {"items": [{"operation_id": "op-1", "kind": "page.insert"}]},
            {"items": []},
        ]
        cursors: list[str | None] = []

        def list_operations(self, cursor: str | None = None) -> dict[str, object]:
            self.cursors.append(cursor)
            return self.pages.pop(0)

    transport = Transport()
    assert client.pull(transport) == [{"operation_id": "op-1", "kind": "page.insert"}]
    assert client.state().remote_operations == 1
    assert client.pending_remote_operations() == [
        {
            "operation_id": "op-1",
            "payload": {"kind": "page.insert", "operation_id": "op-1"},
            "cursor": "op-1",
        }
    ]
    client.mark_remote_applied("op-1")
    assert client.pending_remote_operations() == []
    assert client.pull(transport) == []
    assert transport.cursors == [None, "op-1"]


def test_sync_client_requires_pull_capability(tmp_path: Path) -> None:
    client = SyncClient(tmp_path / "sync.db", enabled=True)

    class Transport:
        pass

    with pytest.raises(SyncTransportError, match="pulling operations"):
        client.pull(Transport())  # type: ignore[arg-type]


def test_resumable_object_staging_and_full_rebuild_preserve_outbox(
    tmp_path: Path,
) -> None:
    database = tmp_path / ".sync" / "outbox.db"
    staging = tmp_path / "staging"
    content = b"resumable-object-content"
    object_id = "sha256:" + sha256(content).hexdigest()
    split = len(content) // 2

    first_process = SyncClient(database, enabled=True)
    partial = first_process.stage_object_chunk(
        object_id,
        content[:split],
        offset=0,
        total_size=len(content),
        staging_root=staging,
    )
    assert partial.name.endswith(".part")
    operation_id = str(uuid4())
    assert first_process.enqueue(operation_id, {"kind": "page.insert"}) is True

    restarted = SyncClient(database, enabled=True)
    completed = restarted.stage_object_chunk(
        object_id,
        content[split:],
        offset=split,
        total_size=len(content),
        staging_root=staging,
    )
    assert completed.read_bytes() == content
    assert restarted.state().pending == 1

    class PullTransport:
        def list_operations(self, cursor: str | None = None) -> dict[str, object]:
            del cursor
            return {
                "items": [
                    {
                        "operation_id": "remote-op-1",
                        "kind": "page.insert",
                    }
                ]
            }

    restarted.pull(PullTransport())  # type: ignore[arg-type]
    assert restarted.state().remote_operations == 1
    restarted.begin_full_rebuild()
    rebuilt = restarted.state()
    assert rebuilt.remote_operations == 0
    assert rebuilt.last_cursor is None
    assert rebuilt.pending == 1


def test_failed_chunk_hash_can_restart_from_zero(tmp_path: Path) -> None:
    client = SyncClient(tmp_path / ".sync" / "outbox.db", enabled=True)
    content = b"correct-content"
    object_id = "sha256:" + sha256(content).hexdigest()
    staging = tmp_path / "staging"

    with pytest.raises(ValueError, match="object hash mismatch"):
        client.stage_object_chunk(
            object_id,
            b"incorrect-data!",
            staging,
            offset=0,
            total_size=len(content),
        )

    recovered = client.stage_object_chunk(
        object_id,
        content,
        staging,
        offset=0,
        total_size=len(content),
    )
    assert recovered.read_bytes() == content
