from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from workbench.ai_models.downloads import ModelDownloadError, ResumableModelDownloader


def test_resumable_download_keeps_partial_bytes_and_verifies_hash(tmp_path: Path) -> None:
    payload = b"abcdefghi"
    downloader = ResumableModelDownloader(tmp_path / "attempt", max_bytes=100)
    calls: list[int] = []

    def interrupted(offset: int):
        calls.append(offset)
        yield payload[offset : offset + 3]
        if offset == 0:
            raise RuntimeError("simulated interruption")

    with pytest.raises(RuntimeError):
        downloader.download_file(
            "model.bin",
            total_bytes=len(payload),
            expected_sha256=hashlib.sha256(payload).hexdigest(),
            chunks=interrupted,
        )
    assert calls == [0]

    completed = downloader.download_file(
        "model.bin",
        total_bytes=len(payload),
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        chunks=lambda offset: [payload[offset:]],
    )
    assert completed.read_bytes() == payload


def test_download_rejects_hash_mismatch_and_unsafe_paths(tmp_path: Path) -> None:
    downloader = ResumableModelDownloader(tmp_path / "attempt", max_bytes=10)
    with pytest.raises(ModelDownloadError, match="hash"):
        downloader.download_file(
            "model.bin",
            total_bytes=3,
            expected_sha256="0" * 64,
            chunks=lambda _offset: [b"abc"],
        )
    with pytest.raises(ModelDownloadError, match="unsafe"):
        downloader.download_file(
            "../escape.bin",
            total_bytes=1,
            expected_sha256="0" * 64,
            chunks=lambda _offset: [b"a"],
        )
