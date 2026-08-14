"""Build a conservative static RC manifest from ordered program stop points."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REQUIRED_TASKS = (
    "A20", "A21", "A22", "A23", "A24", "B20", "B21", "B22", "B23",
    "C20", "C21", "C22", "A30", "B30",
)


class RcManifestError(ValueError):
    """Raised when static RC inputs are incomplete or inconsistent."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _stop_points(root: Path) -> dict[str, dict[str, Any]]:
    directory = root / "docs" / "acceptance" / "foundation" / "stop-points"
    found: dict[str, dict[str, Any]] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise RcManifestError(f"stop_point_invalid:{path.name}") from error
        if not isinstance(value, dict) or not isinstance(value.get("task"), str):
            continue
        task = value["task"]
        if task in REQUIRED_TASKS:
            if task in found:
                raise RcManifestError(f"stop_point_duplicate:{task}")
            if value.get("status") != "ready":
                raise RcManifestError(f"stop_point_not_ready:{task}")
            if not isinstance(value.get("source_commit"), str) or not value["source_commit"]:
                raise RcManifestError(f"stop_point_source_missing:{task}")
            found[task] = {
                "path": path.relative_to(root).as_posix(),
                "sha256": _sha256(path),
                "source_commit": value["source_commit"],
                "title": value.get("title", task),
            }
    missing = [task for task in REQUIRED_TASKS if task not in found]
    if missing:
        raise RcManifestError(f"stop_points_missing:{','.join(missing)}")
    return found


def build_manifest(root: Path, *, candidate_id: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    commit = _git(root, "rev-parse", "HEAD")
    if commit == "unknown":
        raise RcManifestError("git_commit_unavailable")
    stop_points = _stop_points(root)
    dirty = bool(_git(root, "status", "--porcelain"))
    lock_hashes = {
        name: _sha256(root / name)
        for name in ("pnpm-lock.yaml", "uv.lock")
        if (root / name).is_file()
    }
    generated = candidate_id or f"rc-static-{commit[:12]}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    blockers = ["source_worktree_dirty"] if dirty else []
    blockers.extend((
        "pytest_unverified", "windows_a0_a9_unverified", "media_visual_30_pages_unverified",
        "human_signoff_unverified", "external_providers_disabled",
    ))
    return {
        "schema_version": "1.0",
        "candidate_id": generated,
        "status": "static_candidate_blocked" if blockers else "static_candidate_ready_for_runtime_gates",
        "source": {"git_commit": commit, "dirty": dirty, "lock_hashes": lock_hashes},
        "ordered_tasks": list(REQUIRED_TASKS),
        "stop_points": {task: stop_points[task] for task in REQUIRED_TASKS},
        "runtime_evidence": {
            "python_pytest": "unverified", "web_and_playwright": "unverified",
            "windows_a0_a9": "unverified", "media_visual_30_pages": "unverified",
            "human_signoff": "unverified", "external_providers": "disabled",
        },
        "blockers": blockers,
        "freeze_policy": "Any source, lockfile, runtime, flag, installer or evidence change requires a new candidate.",
    }


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a conservative static program RC manifest.")
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-id")
    args = parser.parse_args()
    try:
        manifest = build_manifest(args.repository_root, candidate_id=args.candidate_id)
        write_manifest(args.output, manifest)
    except RcManifestError as error:
        print(f"PROGRAM_RC_MANIFEST=BLOCK reason={error}")
        return 1
    print(f"PROGRAM_RC_MANIFEST={manifest['status']} candidate_id={manifest['candidate_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
