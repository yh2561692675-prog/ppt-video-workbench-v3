from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ObjectStoreError(ValueError):
    pass


class StoredObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    relative_path: str = Field(min_length=1, max_length=500)
    size_bytes: int = Field(ge=0)


class ContentAddressedObjectStore:
    """Hash-addressed storage with staging writes and verified reads."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.objects_root = self.root / "objects"
        self.staging_root = self.root / ".staging"

    def ingest_file(self, source: Path, *, suffix: str | None = None) -> StoredObject:
        if not source.is_file():
            raise ObjectStoreError("source object does not exist")
        self.staging_root.mkdir(parents=True, exist_ok=True)
        temporary = self.staging_root / f"{uuid4().hex}.part"
        digest = hashlib.sha256()
        size = 0
        try:
            with source.open("rb") as input_handle, temporary.open("xb") as output_handle:
                while chunk := input_handle.read(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
                    output_handle.write(chunk)
            content_hash = digest.hexdigest()
            extension = _normalise_suffix(suffix if suffix is not None else source.suffix)
            target = self._object_path(content_hash, extension)
            target.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_contained(target)
            if target.exists():
                temporary.unlink()
            else:
                try:
                    os.replace(temporary, target)
                except FileExistsError:
                    temporary.unlink(missing_ok=True)
            return StoredObject(
                content_hash=content_hash,
                relative_path=target.relative_to(self.root).as_posix(),
                size_bytes=size,
            )
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise ObjectStoreError("unable to store source object") from error

    def open_verified(self, stored: StoredObject) -> Path:
        path = self._resolve_relative(stored.relative_path)
        if not path.is_file():
            raise ObjectStoreError("stored object is missing")
        if self._hash_file(path) != stored.content_hash:
            raise ObjectStoreError("stored object hash does not match")
        if path.stat().st_size != stored.size_bytes:
            raise ObjectStoreError("stored object size does not match")
        return path

    def _object_path(self, content_hash: str, suffix: str) -> Path:
        return self.objects_root / content_hash[:2] / f"{content_hash}{suffix}"

    def _resolve_relative(self, relative_path: str) -> Path:
        path = PurePosixPath(relative_path)
        if path.is_absolute() or ".." in path.parts:
            raise ObjectStoreError("object path must be relative")
        candidate = self.root.joinpath(*path.parts)
        self._ensure_contained(candidate)
        return candidate

    def _ensure_contained(self, candidate: Path) -> None:
        try:
            candidate.resolve(strict=False).relative_to(self.root)
        except ValueError as error:
            raise ObjectStoreError("object path escapes store root") from error

    @staticmethod
    def _hash_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        return digest.hexdigest()


def _normalise_suffix(value: str) -> str:
    if not value:
        return ""
    if not value.startswith(".") or len(value) > 20 or not value[1:].isalnum():
        raise ObjectStoreError("object suffix must be a short alphanumeric extension")
    return value.lower()
