"""Atomic current/previous release pointers kept outside user project data."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


class ReleaseSlotError(RuntimeError):
    """Raised when a release slot cannot be validated or activated."""


@dataclass(frozen=True)
class ReleaseSlot:
    version: str
    relative_path: str
    payload_manifest_sha256: str

    @classmethod
    def from_dict(cls, raw: object) -> ReleaseSlot:
        if not isinstance(raw, dict):
            raise ReleaseSlotError("release_slot_invalid")
        version = raw.get("version")
        relative_path = raw.get("relative_path")
        manifest_hash = raw.get("payload_manifest_sha256")
        if not all(
            isinstance(value, str) and value
            for value in (version, relative_path, manifest_hash)
        ):
            raise ReleaseSlotError("release_slot_invalid")
        assert isinstance(version, str)
        assert isinstance(relative_path, str)
        assert isinstance(manifest_hash, str)
        if Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
            raise ReleaseSlotError("release_slot_path_invalid")
        return cls(version, relative_path, manifest_hash)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class ReleaseSlots:
    """Own current/previous program slots while preserving workspace data."""

    def __init__(self, app_root: Path) -> None:
        self.app_root = app_root.resolve()
        self.releases_root = self.app_root / "releases"
        configured_state_root = os.environ.get("WORKBENCH_STATE_ROOT")
        self.state_root = (
            Path(configured_state_root).resolve()
            if configured_state_root
            else self.app_root.parent / "state"
        )
        self.active_path = self.state_root / "active-release.json"
        self.previous_path = self.state_root / "previous-release.json"

    def slot_for_release(self, release_root: Path, version: str) -> ReleaseSlot:
        release_root = release_root.resolve()
        if not release_root.is_relative_to(self.releases_root):
            raise ReleaseSlotError("release_slot_path_outside_app")
        manifest = release_root / "runtime-manifest.json"
        if not manifest.is_file():
            raise ReleaseSlotError("release_payload_manifest_missing")
        return ReleaseSlot(
            version=version,
            relative_path=release_root.relative_to(self.app_root).as_posix(),
            payload_manifest_sha256=sha256_file(manifest),
        )

    def read_active(self) -> ReleaseSlot:
        return self._read_slot(self.active_path)

    def read_previous(self) -> ReleaseSlot:
        return self._read_slot(self.previous_path)

    def resolve(self, slot: ReleaseSlot) -> Path:
        release_root = (self.app_root / slot.relative_path).resolve()
        if not release_root.is_relative_to(self.releases_root):
            raise ReleaseSlotError("release_slot_path_outside_app")
        manifest = release_root / "runtime-manifest.json"
        if not manifest.is_file():
            raise ReleaseSlotError("release_payload_manifest_missing")
        if sha256_file(manifest) != slot.payload_manifest_sha256:
            raise ReleaseSlotError("release_payload_manifest_hash_mismatch")
        return release_root

    def activate(self, slot: ReleaseSlot) -> None:
        self.resolve(slot)
        previous = self._try_read_slot(self.active_path)
        self._write_slot(self.active_path, slot)
        if previous is not None:
            self._write_slot(self.previous_path, previous)

    def rollback(self) -> ReleaseSlot:
        active = self.read_active()
        previous = self.read_previous()
        self.resolve(previous)
        self._write_slot(self.active_path, previous)
        self._write_slot(self.previous_path, active)
        return previous

    def _read_slot(self, path: Path) -> ReleaseSlot:
        try:
            return ReleaseSlot.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError) as error:
            raise ReleaseSlotError("release_slot_state_invalid") from error

    def _try_read_slot(self, path: Path) -> ReleaseSlot | None:
        try:
            return self._read_slot(path)
        except ReleaseSlotError:
            return None

    def _write_slot(self, path: Path, slot: ReleaseSlot) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".partial")
        temporary.write_text(json.dumps(asdict(slot), indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, path)
