"""Create a candidate identity record before platform packaging."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from workbench.release.feature_policy import load_feature_policy


class CandidateIdentityError(ValueError):
    """Raised when candidate identity inputs cannot be frozen safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise CandidateIdentityError(f"git_command_failed:{args[0]}")
    return result.stdout.strip()


def build_identity(
    repository_root: Path,
    *,
    candidate_id: str,
    feature_policy_path: Path,
    blockers: tuple[str, ...] = (),
) -> dict[str, Any]:
    if not re.fullmatch(r"rc-[A-Za-z0-9][A-Za-z0-9._-]*", candidate_id):
        raise CandidateIdentityError("candidate_id_invalid")
    root = repository_root.resolve()
    policy = load_feature_policy(feature_policy_path)
    if policy.candidate_id not in (None, candidate_id):
        raise CandidateIdentityError("feature_policy_candidate_mismatch")
    dirty = bool(_git(root, "status", "--porcelain", "--untracked-files=all"))
    all_blockers = list(blockers)
    if dirty:
        all_blockers.append("source_worktree_dirty")
    source_commit = _git(root, "rev-parse", "HEAD")
    lock_hashes = {
        name: _sha256(root / name)
        for name in ("uv.lock", "pnpm-lock.yaml")
        if (root / name).is_file()
    }
    relative_policy = feature_policy_path.resolve().relative_to(root).as_posix()
    return {
        "schema_version": "1.0",
        "candidate_id": candidate_id,
        "status": "candidate_frozen" if not all_blockers else "candidate_blocked",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": {
            "git_commit": source_commit,
            "dirty": dirty,
            "lock_hashes": lock_hashes,
        },
        "feature_policy": {
            "relative_path": relative_policy,
            "sha256": _sha256(feature_policy_path),
            "policy_id": policy.policy_id,
        },
        "blocking_failures": sorted(set(all_blockers)),
        "freeze_policy": (
            "Any source, lockfile, runtime, feature policy, installer or evidence "
            "change requires a new candidate."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--feature-policy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--blocker", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        identity = build_identity(
            args.repository_root,
            candidate_id=args.candidate_id,
            feature_policy_path=args.feature_policy,
            blockers=tuple(args.blocker),
        )
    except (CandidateIdentityError, OSError, ValueError) as error:
        print(f"CANDIDATE_IDENTITY=BLOCK reason={error}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(identity, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"CANDIDATE_IDENTITY={identity['status']} candidate_id={identity['candidate_id']}")
    return 0 if identity["status"] == "candidate_frozen" else 1


if __name__ == "__main__":
    raise SystemExit(main())
