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

SOURCE_TOOLS = ("git", "python", "uv", "node", "pnpm")
CAPABILITY_TOOLS = {
    "source": SOURCE_TOOLS,
    "office-import": (*SOURCE_TOOLS, "soffice"),
    "render": (*SOURCE_TOOLS, "ffmpeg", "ffprobe"),
}
TOOLS = tuple(dict.fromkeys(tool for tools in CAPABILITY_TOOLS.values() for tool in tools))


def tool_version(name: str) -> Check:
    executable = shutil.which(name)
    if executable is None:
        return Check(name, "missing", "not found on PATH")
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


def blocking_checks(checks: list[Check], capability: str) -> list[Check]:
    required = {*REQUIRED_FILES, *CAPABILITY_TOOLS[capability]}
    return [
        check
        for check in checks
        if check.name in required and check.status in {"missing", "error"}
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="repository root")
    parser.add_argument(
        "--capability",
        choices=tuple(CAPABILITY_TOOLS),
        default="source",
        help="workbench capability to validate (default: source)",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = args.repo.expanduser().resolve()
    checks = inspect(repo)
    blocking = blocking_checks(checks, args.capability)

    if args.json:
        print(
            json.dumps(
                {
                    "repository": str(repo),
                    "capability": args.capability,
                    "ready": not blocking,
                    "blockers": [check.name for check in blocking],
                    "checks": [asdict(check) for check in checks],
                },
                indent=2,
            )
        )
    else:
        print(f"Repository: {repo}")
        print(f"Capability: {args.capability}")
        for check in checks:
            print(f"[{check.status.upper():16}] {check.name}: {check.detail}")
        if blocking:
            print(f"BLOCKERS: {', '.join(check.name for check in blocking)}")
        print("READY" if not blocking else "BLOCKED")

    return 0 if not blocking else 1


if __name__ == "__main__":
    sys.exit(main())
