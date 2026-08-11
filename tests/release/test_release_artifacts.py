from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.release_artifacts import (
    ArtifactManifestError,
    build_manifest,
    verify_manifest,
    write_manifest,
)


def _payload(root: Path) -> tuple[Path, Path]:
    installer = root / "release" / "setup.exe"
    payload = root / "dist" / "release" / "runtime-manifest.json"
    installer.parent.mkdir(parents=True)
    payload.parent.mkdir(parents=True)
    installer.write_bytes(b"installer")
    payload.write_text("{}", encoding="utf-8")
    return installer, payload


def test_manifest_discovers_installer_from_declared_relative_path(tmp_path: Path) -> None:
    installer, payload = _payload(tmp_path)
    manifest = build_manifest(
        tmp_path,
        installer=installer,
        payload_manifest=payload,
        candidate_id="rc-test",
    )
    manifest_path = tmp_path / "release" / "release-artifacts.json"
    write_manifest(manifest_path, manifest)
    verified = verify_manifest(manifest_path, tmp_path)

    assert verified["candidate_id"] == "rc-test"
    assert manifest["artifacts"]["installer"]["relative_path"] == "release/setup.exe"
    assert not manifest_path.with_name("release-artifacts.json.partial").exists()


def test_manifest_blocks_a_moved_or_replaced_installer(tmp_path: Path) -> None:
    installer, payload = _payload(tmp_path)
    manifest_path = tmp_path / "release" / "release-artifacts.json"
    manifest = build_manifest(
        tmp_path,
        installer=installer,
        payload_manifest=payload,
        candidate_id="rc-test",
    )
    write_manifest(manifest_path, manifest)
    installer.write_bytes(b"tampered!")

    with pytest.raises(ArtifactManifestError, match="installer_hash_mismatch"):
        verify_manifest(manifest_path, tmp_path)


def test_manifest_rejects_paths_that_escape_the_repository(tmp_path: Path) -> None:
    installer, payload = _payload(tmp_path)
    manifest = build_manifest(
        tmp_path,
        installer=installer,
        payload_manifest=payload,
        candidate_id="rc-test",
    )
    manifest["artifacts"]["installer"]["relative_path"] = "../outside.exe"
    manifest_path = tmp_path / "release" / "release-artifacts.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ArtifactManifestError, match="installer_path_outside_repository"):
        verify_manifest(manifest_path, tmp_path)
