"""Create and verify the single source of truth for a Windows release artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"


class ArtifactManifestError(ValueError):
    """Raised when a release artifact manifest is incomplete or unsafe."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative_path(root: Path, path: Path) -> str:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    if not resolved_path.is_relative_to(resolved_root):
        raise ArtifactManifestError("artifact_path_outside_repository")
    return resolved_path.relative_to(resolved_root).as_posix()


def _git_commit(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )
    commit = completed.stdout.strip()
    return commit if completed.returncode == 0 and len(commit) == 40 else "unknown"


def _git_dirty(root: Path) -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
    )
    return completed.returncode != 0 or bool(completed.stdout.strip())


def _lock_hashes(root: Path) -> dict[str, str]:
    return {
        name: sha256_file(root / name)
        for name in ("uv.lock", "pnpm-lock.yaml")
        if (root / name).is_file()
    }


def build_manifest(
    repository_root: Path,
    *,
    installer: Path,
    payload_manifest: Path,
    candidate_id: str | None = None,
    version: str = "0.1.0",
) -> dict[str, Any]:
    root = repository_root.resolve()
    if not installer.is_file():
        raise ArtifactManifestError("installer_file_not_found")
    if not payload_manifest.is_file():
        raise ArtifactManifestError("payload_manifest_not_found")
    commit = _git_commit(root)
    generated_id = candidate_id or (
        f"rc-{commit[:7] if commit != 'unknown' else 'unknown'}-"
        f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    )
    if not generated_id:
        raise ArtifactManifestError("candidate_id_missing")
    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_id": generated_id,
        "version": version,
        "source": {
            "git_commit": commit,
            "dirty": _git_dirty(root),
            "lock_hashes": _lock_hashes(root),
        },
        "artifacts": {
            "installer": {
                "relative_path": _relative_path(root, installer),
                "size": installer.stat().st_size,
                "sha256": sha256_file(installer),
            },
            "payload_manifest": {
                "relative_path": _relative_path(root, payload_manifest),
                "size": payload_manifest.stat().st_size,
                "sha256": sha256_file(payload_manifest),
            },
        },
    }


def _artifact_path(root: Path, record: object, label: str) -> Path:
    if not isinstance(record, dict):
        raise ArtifactManifestError(f"{label}_record_invalid")
    relative_path = record.get("relative_path")
    if not isinstance(relative_path, str) or not relative_path:
        raise ArtifactManifestError(f"{label}_relative_path_invalid")
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root):
        raise ArtifactManifestError(f"{label}_path_outside_repository")
    return candidate


def verify_manifest(path: Path, repository_root: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ArtifactManifestError("artifact_manifest_not_found")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ArtifactManifestError("artifact_manifest_invalid") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA_VERSION:
        raise ArtifactManifestError("artifact_manifest_invalid")
    if not isinstance(manifest.get("candidate_id"), str) or not manifest["candidate_id"]:
        raise ArtifactManifestError("candidate_id_missing")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ArtifactManifestError("artifacts_missing")
    verified: dict[str, str] = {}
    root = repository_root.resolve()
    for label in ("installer", "payload_manifest"):
        record = artifacts.get(label)
        artifact = _artifact_path(root, record, label)
        if not artifact.is_file():
            raise ArtifactManifestError(f"{label}_file_not_found")
        if not isinstance(record, dict):
            raise ArtifactManifestError(f"{label}_record_invalid")
        expected_size = record.get("size")
        expected_hash = record.get("sha256")
        if expected_size != artifact.stat().st_size:
            raise ArtifactManifestError(f"{label}_size_mismatch")
        if not isinstance(expected_hash, str) or sha256_file(artifact) != expected_hash:
            raise ArtifactManifestError(f"{label}_hash_mismatch")
        verified[label] = artifact.as_posix()
    return {"candidate_id": manifest["candidate_id"], "artifacts": verified}


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.partial")
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or verify a release-artifacts manifest.")
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--installer", type=Path)
    parser.add_argument("--payload-manifest", type=Path)
    parser.add_argument("--candidate-id")
    parser.add_argument("--version", default="0.1.0")
    args = parser.parse_args()
    try:
        if args.verify is not None:
            verified = verify_manifest(args.verify, args.repository_root)
            print(f"RELEASE_ARTIFACTS_VERIFY=PASS candidate_id={verified['candidate_id']}")
            return 0
        if args.output is None or args.installer is None or args.payload_manifest is None:
            parser.error("creation requires --output, --installer, and --payload-manifest")
        manifest = build_manifest(
            args.repository_root,
            installer=args.installer,
            payload_manifest=args.payload_manifest,
            candidate_id=args.candidate_id,
            version=args.version,
        )
        write_manifest(args.output, manifest)
        verify_manifest(args.output, args.repository_root)
        print(f"RELEASE_ARTIFACTS_WRITE=PASS candidate_id={manifest['candidate_id']}")
        return 0
    except ArtifactManifestError as error:
        print(f"RELEASE_ARTIFACTS_VERIFY=BLOCK reason={error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
