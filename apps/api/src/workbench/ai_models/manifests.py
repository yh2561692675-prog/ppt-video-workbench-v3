"""Hashing and manifest verification for immutable local model revisions."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from .models import LocalModelDescriptorV1


class ModelManifestError(ValueError):
    """Raised when an installed model does not match its descriptor."""


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(chunk_size):
                digest.update(chunk)
    except OSError as error:
        raise ModelManifestError(f"model file cannot be read: {path.name}") from error
    return digest.hexdigest()


def build_manifest(
    descriptor: LocalModelDescriptorV1,
    model_root: Path,
    *,
    installed_at: datetime | None = None,
) -> dict[str, object]:
    files: list[dict[str, object]] = []
    for declared in descriptor.files:
        target = _safe_child(model_root, declared.relative_path)
        if not target.is_file():
            raise ModelManifestError(f"required model file is missing: {declared.relative_path}")
        actual_size = target.stat().st_size
        actual_hash = sha256_file(target)
        if actual_size != declared.size_bytes or actual_hash != declared.sha256:
            raise ModelManifestError(
                f"model file does not match descriptor: {declared.relative_path}"
            )
        files.append(
            {
                "relative_path": declared.relative_path,
                "size_bytes": actual_size,
                "sha256": actual_hash,
            }
        )
    return {
        "schema_version": 1,
        "model_id": descriptor.model_id,
        "revision": descriptor.revision,
        "engine": descriptor.engine,
        "engine_version": descriptor.engine_version,
        "source_ref": descriptor.source_ref,
        "license_ref": descriptor.license_ref,
        "files": files,
        "installed_at": (installed_at or datetime.now(UTC)).astimezone(UTC).isoformat(),
    }


def verify_model_install(
    descriptor: LocalModelDescriptorV1,
    model_root: Path,
) -> tuple[dict[str, object], str]:
    manifest = build_manifest(descriptor, model_root)
    encoded = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return manifest, hashlib.sha256(encoded).hexdigest()


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.part")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with temporary.open("r+b") as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _safe_child(root: Path, relative_path: str) -> Path:
    candidate = (root / Path(*relative_path.split("/"))).resolve()
    resolved_root = root.resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as error:
        raise ModelManifestError("model file escapes model root") from error
    return candidate
