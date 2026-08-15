"""Fail-closed binding check for a release candidate and its evidence files."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


class CandidateEvidenceError(ValueError):
    """Raised for malformed or cross-candidate release evidence."""


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CandidateEvidenceError(f"{label}_invalid") from error
    if not isinstance(value, dict):
        raise CandidateEvidenceError(f"{label}_object_required")
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


def _relative_evidence_refs(value: object) -> list[str]:
    refs: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"evidence_refs", "artifact_refs", "log_refs"} and isinstance(item, list):
                refs.extend(str(ref) for ref in item if isinstance(ref, str))
            refs.extend(_relative_evidence_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.extend(_relative_evidence_refs(item))
    return refs


def _unsafe_reference(reference: str) -> bool:
    """Recognize POSIX and Windows absolute/traversal refs on every host."""

    normalized = reference.replace("\\", "/")
    posix = PurePosixPath(normalized)
    windows = PureWindowsPath(reference)
    return (
        posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or ".." in posix.parts
        or ".." in windows.parts
    )


def verify_candidate(candidate_path: Path, evidence_paths: tuple[Path, ...]) -> dict[str, Any]:
    candidate = _load(candidate_path, "candidate_manifest")
    candidate_id = candidate.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        raise CandidateEvidenceError("candidate_id_missing")
    source = candidate.get("source")
    blockers: list[str] = []
    if not isinstance(source, Mapping) or not isinstance(source.get("git_commit"), str):
        blockers.append("source_commit_missing")
    if isinstance(source, Mapping) and source.get("dirty") is not False:
        blockers.append("source_worktree_dirty")
    if not evidence_paths:
        blockers.append("evidence_missing")
    reports: list[dict[str, Any]] = []
    for path in evidence_paths:
        evidence = _load(path, f"evidence:{path.name}")
        ids = _candidate_ids(evidence)
        if not ids:
            blockers.append(f"candidate_id_missing:{path.name}")
        elif any(value != candidate_id for value in ids):
            blockers.append(f"candidate_id_mismatch:{path.name}")
        if evidence.get("decision") not in (None, "pass"):
            blockers.append(f"decision_not_passed:{path.name}")
        failures = evidence.get("blocking_failures")
        if isinstance(failures, list) and failures:
            blockers.append(f"blocking_failures:{path.name}")
        signoff = evidence.get("signoff")
        if isinstance(signoff, Mapping) and signoff.get("signed") is not True:
            blockers.append(f"signoff_missing:{path.name}")
        for reference in _relative_evidence_refs(evidence):
            if _unsafe_reference(reference):
                blockers.append(f"evidence_path_outside_root:{path.name}")
                break
        reports.append({"path": path.as_posix(), "candidate_ids": sorted(set(ids))})
    return {"schema_version": "1.0", "candidate_id": candidate_id, "status": "candidate_evidence_ready" if not blockers else "candidate_evidence_blocked", "blockers": sorted(set(blockers)), "evidence": reports}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify release candidate evidence binding.")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, action="append", default=[])
    args = parser.parse_args()
    try:
        report = verify_candidate(args.candidate, tuple(args.evidence))
    except CandidateEvidenceError as error:
        print(f"RC_EVIDENCE=BLOCK reason={error}")
        return 1
    print(f"RC_EVIDENCE={report['status']} candidate_id={report['candidate_id']}")
    if report["blockers"]:
        print("RC_EVIDENCE_BLOCKERS=" + ",".join(report["blockers"]))
    return 0 if report["status"] == "candidate_evidence_ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
