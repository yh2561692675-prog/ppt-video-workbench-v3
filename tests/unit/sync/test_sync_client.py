from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from workbench.sync import SyncClient


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
