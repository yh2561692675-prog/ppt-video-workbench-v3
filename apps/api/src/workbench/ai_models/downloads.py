"""Network-agnostic resumable model download primitive.

The transport is injected so production can use a reviewed downloader while
tests and offline installs remain fully local and deterministic.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Callable, Iterable
from pathlib import Path


class ModelDownloadError(RuntimeError):
    pass


class ResumableModelDownloader:
    def __init__(self, attempt_root: Path, *, max_bytes: int) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.attempt_root = attempt_root
        self.max_bytes = max_bytes
        self.attempt_root.mkdir(parents=True, exist_ok=True)

    def preflight_disk(self, expected_bytes: int) -> None:
        if expected_bytes < 0 or expected_bytes > self.max_bytes:
            raise ModelDownloadError("download_budget_exceeded")
        free = shutil.disk_usage(self.attempt_root.parent).free
        if free < expected_bytes:
            raise ModelDownloadError("insufficient_disk_space")

    def download_file(
        self,
        relative_path: str,
        *,
        total_bytes: int,
        expected_sha256: str,
        chunks: Callable[[int], Iterable[bytes]],
        progress: Callable[[int, int], None] | None = None,
    ) -> Path:
        self.preflight_disk(total_bytes)
        if (
            "\\" in relative_path
            or relative_path.startswith("/")
            or ".." in Path(relative_path).parts
        ):
            raise ModelDownloadError("unsafe_download_path")
        target = (self.attempt_root / Path(*relative_path.split("/"))).resolve()
        try:
            target.relative_to(self.attempt_root.resolve())
        except ValueError as error:
            raise ModelDownloadError("unsafe_download_path") from error
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_suffix(target.suffix + ".part")
        offset = part.stat().st_size if part.exists() else 0
        if offset > total_bytes:
            part.unlink()
            offset = 0
        with part.open("ab") as handle:
            for chunk in chunks(offset):
                if not isinstance(chunk, bytes):
                    raise ModelDownloadError("download_chunk_not_bytes")
                offset += len(chunk)
                if offset > total_bytes or offset > self.max_bytes:
                    raise ModelDownloadError("download_budget_exceeded")
                handle.write(chunk)
                handle.flush()
                if progress is not None:
                    progress(offset, total_bytes)
            os.fsync(handle.fileno())
        if offset != total_bytes:
            raise ModelDownloadError("download_incomplete")
        digest = hashlib.sha256(part.read_bytes()).hexdigest()
        if digest != expected_sha256:
            part.unlink(missing_ok=True)
            raise ModelDownloadError("download_hash_mismatch")
        os.replace(part, target)
        return target
