"""Run four fail-closed personal-use preflight gates.

The report is deliberately independent of the UI project snapshot. It binds
source, candidate, runtime, and PPT input fingerprints so an old report cannot
authorize a changed render.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

GATES = ("source", "build", "runtime", "project")
LOCKFILES = ("uv.lock", "pnpm-lock.yaml")
RUNTIME_TOOLS = ("node", "ffmpeg", "ffprobe")


class PreflightContractError(ValueError):
    """Raised when preflight inputs cannot be safely evaluated."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def git_output(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _gate(status: str, reasons: list[str], metrics: dict[str, Any], evidence: list[str] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "reason_codes": sorted(set(reasons)),
        "evidence_refs": evidence or [],
        "metrics": metrics,
    }


def build_report(
    repository_root: Path,
    *,
    candidate_id: str,
    project_input: Path | None = None,
    output_root: Path | None = None,
    report_id: str | None = None,
) -> dict[str, Any]:
    root = repository_root.resolve()
    commit = git_output(root, "rev-parse", "HEAD")
    dirty = bool(git_output(root, "status", "--porcelain"))
    if not commit:
        raise PreflightContractError("source_commit_unavailable")
    project_path = project_input.resolve() if project_input else None
    project_fingerprint = (
        canonical_hash({"path": project_path.as_posix(), "sha256": sha256_file(project_path)})
        if project_path and project_path.is_file()
        else canonical_hash({"project_input": "missing"})
    )
    config = {
        "candidate_id": candidate_id,
        "source_commit": commit,
        "locks": {
            name: sha256_file(root / name)
            for name in LOCKFILES
            if (root / name).is_file()
        },
        "project_input": project_path.as_posix() if project_path else None,
        "output_root": output_root.resolve().as_posix() if output_root else None,
    }
    config_hash = canonical_hash(config)

    source_reasons: list[str] = []
    if dirty:
        source_reasons.append("source_worktree_dirty")
    source_gate = _gate("passed" if not source_reasons else "blocked", source_reasons, {"git_commit": commit, "dirty": dirty})

    build_reasons: list[str] = []
    if not candidate_id.startswith("rc-"):
        build_reasons.append("release_candidate_id_required")
    missing_locks = [name for name in LOCKFILES if not (root / name).is_file()]
    if missing_locks:
        build_reasons.append("lockfile_missing")
    build_gate = _gate("passed" if not build_reasons else "blocked", build_reasons, {"lockfiles": config["locks"]})

    runtime_reasons: list[str] = []
    runtime_paths: dict[str, str] = {"python": sys.executable}
    for name in RUNTIME_TOOLS:
        resolved = shutil.which(name)
        if resolved:
            runtime_paths[name] = resolved
        else:
            runtime_reasons.append(f"runtime_tool_missing:{name}")
    runtime_gate = _gate("passed" if not runtime_reasons else "blocked", runtime_reasons, {"tools": runtime_paths})

    project_reasons: list[str] = []
    project_metrics: dict[str, Any] = {"input_fingerprint": project_fingerprint}
    if project_path is None or not project_path.is_file():
        project_reasons.append("project_input_missing")
    elif project_path.suffix.casefold() not in {".pptx", ".pptm", ".ppsx", ".ppt"}:
        project_reasons.append("project_input_not_powerpoint")
    else:
        project_metrics.update({"input_path": project_path.as_posix(), "input_sha256": sha256_file(project_path), "size_bytes": project_path.stat().st_size})
    if output_root is None:
        project_reasons.append("output_root_missing")
    else:
        try:
            output_root.mkdir(parents=True, exist_ok=True)
            probe = output_root / f".preflight-write-{uuid4().hex}.tmp"
            probe.write_text("preflight", encoding="utf-8")
            probe.unlink()
            project_metrics["output_root"] = output_root.resolve().as_posix()
        except OSError:
            project_reasons.append("output_root_not_writable")
    project_gate = _gate("passed" if not project_reasons else "blocked", project_reasons, project_metrics)

    gates = {"source": source_gate, "build": build_gate, "runtime": runtime_gate, "project": project_gate}
    status = "passed" if all(gate["status"] == "passed" for gate in gates.values()) else "blocked"
    return {
        "schema_version": "1.0",
        "report_id": report_id or f"preflight-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}",
        "candidate_id": candidate_id,
        "source_commit": commit,
        "input_fingerprint": project_fingerprint,
        "config_hash": config_hash,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": status,
        "gates": gates,
    }


def is_stale(report: dict[str, Any], current: dict[str, Any]) -> bool:
    return any(report.get(key) != current.get(key) for key in ("candidate_id", "source_commit", "input_fingerprint", "config_hash"))


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.partial")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = build_report(args.repository_root, candidate_id=args.candidate_id, project_input=args.input, output_root=args.output_root)
        write_report(args.output, report)
    except PreflightContractError as error:
        print(f"PERSONAL_USE_PREFLIGHT=BLOCK reason={error}")
        return 1
    print(f"PERSONAL_USE_PREFLIGHT={report['status'].upper()} report={args.output}")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
