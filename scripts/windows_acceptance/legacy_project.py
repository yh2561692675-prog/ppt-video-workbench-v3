from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from scripts.windows_acceptance.evidence import write_json_atomic


class LegacyProjectError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inspect_legacy_project(source: Path) -> dict[str, object]:
    root = source.resolve()
    manifest_path = root / "project.json"
    if not manifest_path.is_file():
        raise LegacyProjectError("legacy_project_manifest_missing")
    try:
        manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise LegacyProjectError("legacy_project_manifest_invalid") from error
    if not isinstance(manifest.get("id"), str) or not isinstance(
        manifest.get("schema_version"), int
    ):
        raise LegacyProjectError("legacy_project_identity_invalid")
    protected: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name not in {"project.json", "legacy-copy-manifest.json"}:
            protected.append(
                {
                    "relative_path": path.relative_to(root).as_posix(),
                    "size": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    pages = manifest.get("pages")
    audio_count = sum(
        1 for page in pages if isinstance(page, dict) and isinstance(page.get("audio"), dict)
    ) if isinstance(pages, list) else 0
    subtitle = manifest.get("subtitle_artifact")
    return {
        "schema_version": "1.0",
        "project_id": manifest["id"],
        "project_schema_version": manifest["schema_version"],
        "page_count": len(pages) if isinstance(pages, list) else 0,
        "audio_count": audio_count,
        "has_subtitles": isinstance(subtitle, dict),
        "protected_files": protected,
    }


def copy_and_verify_legacy_project(source: Path, destination: Path) -> dict[str, object]:
    source_summary = inspect_legacy_project(source)
    source_root = source.resolve()
    target = destination.resolve()
    if target == source_root or source_root in target.parents:
        raise LegacyProjectError("legacy_copy_destination_invalid")
    if target.exists():
        raise LegacyProjectError("legacy_copy_destination_exists")
    shutil.copytree(source_root, target, copy_function=shutil.copy2)
    copied_summary = inspect_legacy_project(target)
    if copied_summary["protected_files"] != source_summary["protected_files"]:
        raise LegacyProjectError("legacy_copy_hash_mismatch")
    copy_manifest: dict[str, object] = {
        "schema_version": "1.0",
        "source_summary": source_summary,
        "copy_summary": copied_summary,
        "source_write_probe": "not_attempted_read_only",
    }
    write_json_atomic(target / "legacy-copy-manifest.json", copy_manifest)
    return copy_manifest


def verify_legacy_copy(copy_root: Path, copy_manifest: Path | None = None) -> dict[str, object]:
    root = copy_root.resolve()
    manifest_path = copy_manifest or root / "legacy-copy-manifest.json"
    try:
        record = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected = record["copy_summary"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise LegacyProjectError("legacy_copy_manifest_invalid") from error
    actual = inspect_legacy_project(root)
    if actual["project_id"] != expected.get("project_id"):
        raise LegacyProjectError("legacy_project_id_changed")
    if actual["protected_files"] != expected.get("protected_files"):
        raise LegacyProjectError("legacy_protected_file_changed")
    return actual
