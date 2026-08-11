"""Fail-closed DP20 release payload and runtime preflight."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .models import load_and_validate, validate_candidate_manifest


def _probe(path: Path | None, *arguments: str) -> dict[str, Any]:
    if path is None:
        return {"available": False}
    try:
        result = subprocess.run(
            [str(path), *arguments], capture_output=True, text=True, timeout=20, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"available": False, "path": str(path), "error": str(error)}
    lines = (result.stdout or result.stderr).splitlines()
    return {
        "available": result.returncode == 0,
        "path": str(path),
        "exit_code": result.returncode,
        "identity": lines[0][:240] if lines else "",
    }


def run_preflight(repo_root: Path, candidate: Path) -> tuple[dict[str, Any], int]:
    repo_root = repo_root.resolve()
    manifest = load_and_validate(candidate, validate_candidate_manifest, candidate.parent)
    reasons: list[str] = []
    required_files = (
        "runtime-assets/node/node.exe",
        "runtime-assets/ffmpeg/ffmpeg.exe",
        "runtime-assets/ffmpeg/ffprobe.exe",
        "runtime-assets/remotion/node_modules/@remotion/cli/remotion-cli.js",
        "runtime-assets/remotion/src/index.ts",
        "scripts/build-release.ps1",
        "scripts/build_runtime_manifest.py",
        "scripts/release_artifacts.py",
        "installer/workbench.iss",
    )
    missing = [relative for relative in required_files if not (repo_root / relative).is_file()]
    if missing:
        reasons.append("missing release inputs: " + ", ".join(missing))
    if shutil.which("ISCC.exe") is None:
        reasons.append("ISCC.exe is unavailable; installer cannot be generated")
    historical = repo_root / "release/ppt-video-workbench-setup.exe"
    if historical.is_file():
        reasons.append("historical installer exists; reuse is forbidden")
    tools = {name: shutil.which(name) for name in ("uv", "pnpm", "node", "ffmpeg", "ffprobe")}
    unavailable_tools = [name for name, path in tools.items() if path is None]
    if unavailable_tools:
        reasons.append("missing tools: " + ", ".join(unavailable_tools))
    iscc_path = shutil.which("ISCC.exe")
    remotion_path = repo_root / "runtime-assets/remotion/node_modules/@remotion/cli/remotion-cli.js"
    launcher_path = repo_root / "dist/release/launcher/workbench-launcher.exe"
    payload = {
        "schema_version": "1.0",
        "candidate_id": manifest["candidate_id"],
        "source_commit": manifest["source"]["commit"],
        "status": "passed" if not reasons else "blocked",
        "required_files": list(required_files),
        "missing": missing,
        "tools": tools,
        "identity_probes": {
            "node": _probe(Path(tools["node"]) if tools["node"] else None, "--version"),
            "ffmpeg": _probe(Path(tools["ffmpeg"]) if tools["ffmpeg"] else None, "-version"),
            "ffprobe": _probe(Path(tools["ffprobe"]) if tools["ffprobe"] else None, "-version"),
            "iscc": _probe(Path(iscc_path) if iscc_path else None, "/?"),
            "remotion": {
                "available": remotion_path.is_file(),
                "path": "runtime-assets/remotion/node_modules/@remotion/cli/remotion-cli.js",
            },
            "launcher": {
                "available": launcher_path.is_file(),
                "path": "dist/release/launcher/workbench-launcher.exe",
            },
        },
        "reasons": reasons,
        "installer_reuse": False,
    }
    return payload, 0 if not reasons else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--candidate", type=Path, required=True)
    args = parser.parse_args()
    payload, exit_code = run_preflight(args.repo_root, args.candidate)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
