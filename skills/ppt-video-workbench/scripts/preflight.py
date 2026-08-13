#!/usr/bin/env python3
"""Read-only repository and tool preflight for PPT Video Workbench."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


REQUIRED_FILES = (
    "pyproject.toml",
    "uv.lock",
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "apps/api/pyproject.toml",
    "apps/web/package.json",
    "remotion/package.json",
)

TOOLS = ("git", "python", "uv", "node", "pnpm", "ffmpeg", "ffprobe", "soffice")


def tool_version(name: str) -> Check:
    executable = shutil.which(name)
    if executable is None:
        required = name not in {"ffmpeg", "ffprobe", "soffice"}
        return Check(name, "missing" if required else "optional-missing", "not found on PATH")
    commands = {
        "ffmpeg": [executable, "-version"],
        "ffprobe": [executable, "-version"],
        "soffice": [executable, "--version"],
        "pnpm": [executable, "--version"],
    }
    command = commands.get(name, [executable, "--version"])
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Check(name, "error", str(exc))
    output = (result.stdout or result.stderr).strip().splitlines()
    detail = output[0] if output else f"exit code {result.returncode}"
    return Check(name, "ok" if result.returncode == 0 else "error", detail)


def inspect(repo: Path) -> list[Check]:
    checks: list[Check] = []
    for relative in REQUIRED_FILES:
        path = repo / relative
        checks.append(Check(relative, "ok" if path.is_file() else "missing", str(path)))
    checks.extend(tool_version(name) for name in TOOLS)
    return checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = args.repo.expanduser().resolve()
    checks = inspect(repo)
    blocking = [check for check in checks if check.status in {"missing", "error"}]

    if args.json:
        print(
            json.dumps(
                {
                    "repository": str(repo),
                    "ready": not blocking,
                    "checks": [asdict(check) for check in checks],
                },
                indent=2,
            )
        )
    else:
        print(f"Repository: {repo}")
        for check in checks:
            print(f"[{check.status.upper():16}] {check.name}: {check.detail}")
        print("READY" if not blocking else "BLOCKED")

    return 0 if not blocking else 1


if __name__ == "__main__":
    sys.exit(main())
