"""Check CI wiring and require evidence from an external runner for DP24."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument(
        "--external-evidence",
        type=Path,
        help="validated evidence emitted by a completed Windows/Ubuntu CI matrix",
    )
    args = parser.parse_args()
    workflow = (args.repo_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    checks = {
        "ubuntu_and_windows_matrix": "ubuntu-latest" in workflow and "windows-latest" in workflow,
        "explicit_pnpm_e2e": "pnpm e2e" in workflow,
        "no_continue_on_error": "continue-on-error" not in workflow,
    }
    external_runner = "not executed locally; CI evidence remains required"
    if args.external_evidence is not None:
        evidence = args.external_evidence.resolve()
        if not evidence.is_file() or not evidence.is_relative_to(args.repo_root.resolve()):
            external_runner = "external evidence path is missing or outside repo-root"
        else:
            relative = evidence.relative_to(args.repo_root.resolve()).as_posix()
            external_runner = f"evidence file present: {relative}"
    checks["external_runner_evidence"] = (
        args.external_evidence is not None
        and external_runner.startswith("evidence file present:")
    )
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
