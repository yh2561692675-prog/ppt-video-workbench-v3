"""Aggregate fail-closed evidence for one personal-use release candidate."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class PersonalUseClosureError(ValueError):
    """Raised when a closure input is malformed."""


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PersonalUseClosureError(f"{label}_invalid") from error
    if not isinstance(value, dict):
        raise PersonalUseClosureError(f"{label}_object_required")
    return value


def _candidate_ids(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "candidate_id" and isinstance(item, str) and item:
                found.append(item)
            found.extend(_candidate_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_candidate_ids(item))
    return found


def _refs(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"evidence_refs", "artifact_refs", "log_refs"} and isinstance(item, list):
                found.extend(reference for reference in item if isinstance(reference, str))
            found.extend(_refs(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_refs(item))
    return found


def aggregate_closure(candidate_path: Path, evidence_paths: tuple[Path, ...]) -> dict[str, Any]:
    candidate = _load(candidate_path, "candidate_manifest")
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id.startswith("rc-"):
        raise PersonalUseClosureError("candidate_id_missing_or_invalid")
    blockers: list[str] = []
    source = candidate.get("source")
    if not isinstance(source, Mapping) or not isinstance(source.get("git_commit"), str):
        blockers.append("source_commit_missing")
    if isinstance(source, Mapping) and source.get("dirty") is not False:
        blockers.append("source_worktree_dirty")
    if not evidence_paths:
        blockers.append("evidence_missing")
    evidence: list[dict[str, Any]] = []
    for path in evidence_paths:
        report = _load(path, f"evidence:{path.name}")
        ids = sorted(set(_candidate_ids(report)))
        if not ids:
            blockers.append(f"candidate_id_missing:{path.name}")
        elif ids != [candidate_id]:
            blockers.append(f"candidate_id_mismatch:{path.name}")
        if report.get("status") not in {"passed", "candidate_evidence_ready"}:
            blockers.append(f"stage_not_passed:{path.name}")
        failures = report.get("blocking_failures")
        if isinstance(failures, list) and failures:
            blockers.append(f"blocking_failures:{path.name}")
        unsafe_refs = [
            ref for ref in _refs(report) if Path(ref).is_absolute() or ".." in Path(ref).parts
        ]
        if unsafe_refs:
            blockers.append(f"evidence_path_outside_root:{path.name}")
        evidence.append(
            {
                "path": path.as_posix(),
                "stage": report.get("stage", report.get("schema_version", "unknown")),
                "status": report.get("status"),
                "candidate_ids": ids,
            }
        )
    ready = not blockers
    return {
        "schema_version": "1.0",
        "candidate_id": candidate_id,
        "status": "personal_use_ready" if ready else "personal_use_blocked",
        "decision": "pass" if ready else "blocked",
        "blocking_failures": sorted(set(blockers)),
        "evidence": evidence,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument(
        "--evidence", "--stage", dest="evidence", type=Path, action="append", default=[]
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = aggregate_closure(args.candidate, tuple(args.evidence))
    except PersonalUseClosureError as error:
        print(f"PERSONAL_USE_CLOSURE=BLOCK reason={error}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"PERSONAL_USE_CLOSURE={report['status']} candidate_id={report['candidate_id']}")
    if report["blocking_failures"]:
        print("PERSONAL_USE_CLOSURE_BLOCKERS=" + ",".join(report["blocking_failures"]))
    return 0 if report["status"] == "personal_use_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
