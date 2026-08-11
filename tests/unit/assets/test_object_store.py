from __future__ import annotations

from pathlib import Path

import pytest
from workbench.assets.object_store import ContentAddressedObjectStore, ObjectStoreError


def test_object_store_reuses_content_and_verifies_the_published_object(tmp_path: Path) -> None:
    source = tmp_path / "source file.txt"
    source.write_bytes(b"same source bytes")
    store = ContentAddressedObjectStore(tmp_path / "asset-store")

    first = store.ingest_file(source)
    second = store.ingest_file(source)

    assert second == first
    assert store.open_verified(first).read_bytes() == b"same source bytes"
    assert source.read_bytes() == b"same source bytes"


def test_object_store_rejects_tampering_and_escape_paths(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    source.write_bytes(b"original")
    store = ContentAddressedObjectStore(tmp_path / "asset-store")
    stored = store.ingest_file(source)
    object_path = store.open_verified(stored)
    object_path.write_bytes(b"tampered")

    with pytest.raises(ObjectStoreError, match="hash"):
        store.open_verified(stored)
    with pytest.raises(ObjectStoreError, match="relative"):
        store._resolve_relative("../outside.bin")
