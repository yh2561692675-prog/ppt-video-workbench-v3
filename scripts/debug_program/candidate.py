"""Create a clean, content-addressed CandidateManifestV1 snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import ValidationError, validate_candidate_manifest

SNAPSHOT_FILES = (
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    "pyproject.toml",
    "uv.lock",
    "packages/contracts/openapi.json",
    "packages/contracts/v1-contract-catalog.json",
    "packages/contracts/project.schema.json",
    "schemas/cloud/cloud-collaboration-v1.openapi.yaml",
    "schemas/render-graph-v2.schema.json",
    "schemas/export-plan-v1.schema.json",
    "schemas/performance-budget-v1.schema.json",
    "schemas/quality-report-v1.schema.json",
    "apps/api/src/workbench/contracts/core_compat.py",
)


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def validate_checkout(candidate: dict[str, Any], repo_root: Path) -> None:
    """Bind an automation run to the exact clean checkout used for the candidate."""

    repo_root = repo_root.resolve()
    if not repo_root.is_dir():
        raise ValidationError("repo_root is not a directory")
    try:
        checkout = Path(_git(repo_root, "rev-parse", "--show-toplevel")).resolve()
        head = _git(repo_root, "rev-parse", "HEAD")
        dirty = _git(repo_root, "status", "--porcelain=v1", "--untracked-files=all")
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValidationError(f"repo_root is not a usable git checkout: {exc}") from exc
    if checkout != repo_root:
        raise ValidationError("repo_root does not resolve to the git checkout root")
    if head != candidate["source"]["commit"]:
        raise ValidationError("repo HEAD does not match candidate source commit")
    if dirty:
        raise ValidationError("repo checkout is dirty; automation is fail-closed")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ref(path: Path, root: Path) -> dict[str, Any]:
    return {
        "path": path.relative_to(root).as_posix(),
        "size": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _probe(command: str, *args: str) -> dict[str, Any]:
    path = shutil.which(command)
    if path is None:
        return {"available": False, "command": command}
    return _probe_path(Path(path), command, *args)


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve())
    except OSError:
        return str(path.absolute())


def _probe_path(path: Path, command: str, *args: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [str(path), *args], capture_output=True, text=True, timeout=20, check=False
        )
        output = (result.stdout or result.stderr).splitlines()
        identity = output[0][:240] if output else ""
        available = result.returncode == 0 or (
            command.lower() == "iscc.exe" and "inno setup" in identity.lower()
        )
        return {
            "available": available,
            "path": _display_path(path),
            "exit_code": result.returncode,
            "version": identity,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        # Runtime discovery is evidence, never a precondition for snapshotting
        # a clean source candidate.  Windows may deny execution of a locally
        # installed tool (for example ISCC under policy); retain the exact
        # probe failure and let the later release gate block on availability.
        return {"available": False, "path": _display_path(path), "error": str(exc)}


def resolve_iscc_path() -> Path | None:
    configured = shutil.which("ISCC.exe")
    if configured:
        return Path(configured)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        fallback = Path(local_app_data) / "Programs" / "Inno Setup 6" / "ISCC.exe"
        try:
            if fallback.is_file():
                return fallback
        except OSError:
            # The subsequent probe records the inaccessible runtime. Candidate
            # creation must remain a source snapshot operation, not a tool
            # execution authorization check.
            return fallback
    return None


def build_candidate(repo_root: Path, output_root: Path, candidate_id: str | None = None) -> Path:
    repo_root = repo_root.resolve()
    output_root = output_root.resolve()
    dirty = bool(_git(repo_root, "status", "--porcelain=v1", "--untracked-files=all"))
    if dirty:
        raise RuntimeError("source worktree is dirty; candidate generation is fail-closed")
    commit = _git(repo_root, "rev-parse", "HEAD")
    branch = _git(repo_root, "branch", "--show-current")
    timestamp = datetime.now(UTC).replace(microsecond=0)
    stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
    candidate_id = candidate_id or f"v1-rc-{commit[:12]}-{stamp}"
    candidate_root = output_root / candidate_id
    candidate_root.mkdir(parents=True, exist_ok=False)
    try:
        snapshot_root = candidate_root / "source"
        snapshot_root.mkdir()
        refs: list[dict[str, Any]] = []
        missing: list[str] = []
        for relative in SNAPSHOT_FILES:
            source = repo_root / relative
            if not source.is_file():
                missing.append(relative)
                continue
            destination = snapshot_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            refs.append(_ref(destination, candidate_root))
        if missing:
            raise RuntimeError(
                "required candidate snapshot files are missing: " + ", ".join(missing)
            )
        runtime = {
        "python": _probe("python", "--version"),
        "node": _probe("node", "--version"),
        "pnpm": _probe("pnpm", "--version"),
        "ffmpeg": _probe("ffmpeg", "-version"),
        "ffprobe": _probe("ffprobe", "-version"),
        "iscc": (
            _probe_path(iscc_path, "ISCC.exe", "/?")
            if (iscc_path := resolve_iscc_path()) is not None
            else {"available": False, "command": "ISCC.exe"}
        ),
        "remotion_cli": {
            "available": (repo_root / "node_modules/.bin/remotion").is_file()
            or (repo_root / "remotion/node_modules/.bin/remotion").is_file()
        },
        "launcher": {
            "available": (
                repo_root / "dist/release/launcher/workbench-launcher.exe"
            ).is_file()
        },
        }
        manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "candidate_id": candidate_id,
        "generated_at": timestamp.isoformat().replace("+00:00", "Z"),
        "source": {"commit": commit, "branch": branch, "dirty": False},
        "files": refs,
        "runtime": runtime,
        "features": {
            "contract_set_sha256": (
                "de55cc1090e49b0ab4d7fb6375b4509cb878d5888e8bef54fd00407a34fbebf6"
            ),
            "missing_snapshot_files": missing,
            "installer_required_for_release": True,
        },
        }
        validate_candidate_manifest(manifest, candidate_root)
        manifest_path = candidate_root / "candidate-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return manifest_path
    except BaseException:
        shutil.rmtree(candidate_root, ignore_errors=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument(
        "--output-root", type=Path, default=Path("test-results/debug-program/candidates")
    )
    parser.add_argument("--candidate-id")
    args = parser.parse_args()
    path = build_candidate(args.repo_root, args.output_root, args.candidate_id)
    print(json.dumps({"candidate": str(path), "candidate_id": path.parent.name}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
