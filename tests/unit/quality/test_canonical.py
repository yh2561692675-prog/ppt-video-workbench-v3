from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from workbench.quality.canonical import canonical_hash, file_hash


def test_canonical_hash_is_order_independent_for_mapping(tmp_path: Path) -> None:
    assert canonical_hash({"b": 2, "a": 1}) == canonical_hash({"a": 1, "b": 2})


def test_file_hash_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "video.mp4"
    path.write_bytes(b"fixture")
    assert file_hash(path) == file_hash(path)
    assert len(file_hash(path)) == 64
    assert uuid4() is not None
