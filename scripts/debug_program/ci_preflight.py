"""Check CI wiring and require evidence from an external runner for DP24."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

from .ci_evidence import validate_external_ci_evidence
from .models import ValidationError


def _git_head(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValidationError(f"cannot read checkout HEAD: {exc}") from exc
    head = completed.stdout.strip()
    if len(head) != 40 or any(char not in "0123456789abcdef" for char in head):
        raise ValidationError("checkout HEAD is not a 40-character lowercase commit")
    return head


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument(
        "--candidate",
        type=Path,
        help="candidate-manifest.json bound to the external CI attestation",
    )
    parser.add_argument(
        "--external-evidence",
        type=Path,
        help="validated evidence emitted by a completed Windows/Ubuntu CI matrix",
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    try:
        workflow_path = repo_root / ".github/workflows/ci.yml"
        workflow = workflow_path.read_text(encoding="utf-8")
    except OSError as exc:
        payload = {
            "schema_version": "1.0",
            "status": "blocked",
            "checks": {},
            "external_runner": f"cannot read CI workflow: {exc}",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    checks = {
        "ubuntu_and_windows_matrix": "ubuntu-latest" in workflow and "windows-latest" in workflow,
        "explicit_pnpm_e2e": "pnpm e2e" in workflow,
        "no_continue_on_error": "continue-on-error" not in workflow,
    }
    external_runner = "not executed locally; CI evidence remains required"
    if args.external_evidence is not None and args.candidate is None:
        external_runner = "candidate is required when external CI evidence is supplied"
    elif args.external_evidence is not None:
        evidence = args.external_evidence.resolve()
        candidate = args.candidate.resolve()
        if not evidence.is_file() or not evidence.is_relative_to(repo_root):
            external_runner = "external evidence path is missing or outside repo-root"
        else:
            try:
                raw = json.loads(evidence.read_text(encoding="utf-8"))
                validated = validate_external_ci_evidence(
                    raw,
                    evidence,
                    repo_root,
                    candidate,
                    _git_head(repo_root),
                )
                relative = evidence.relative_to(repo_root).as_posix()
                external_runner = f"validated external evidence: {relative}"
                checks["external_evidence_schema"] = True
                checks["external_evidence_candidate"] = bool(validated["candidate_id"])
            except (OSError, json.JSONDecodeError, ValidationError) as exc:
                external_runner = f"external evidence rejected: {exc}"
                checks["external_evidence_schema"] = False
    checks["external_runner_evidence"] = external_runner.startswith("validated external evidence:")
    payload = {
        "schema_version": "1.0",
        "status": "passed" if all(checks.values()) else "blocked",
        "checks": checks,
        "external_runner": external_runner,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
