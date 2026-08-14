from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("verify_candidate_evidence", ROOT / "scripts" / "verify_candidate_evidence.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _candidate(tmp_path: Path, *, candidate_id: str = "rc-test") -> Path:
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps({"candidate_id": candidate_id, "source": {"git_commit": "a" * 40, "dirty": False}}), encoding="utf-8")
    return path


def test_evidence_is_bound_to_one_clean_candidate(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps({"release": {"candidate_id": "rc-test"}, "decision": "pass"}), encoding="utf-8")
    report = MODULE.verify_candidate(candidate, (evidence,))
    assert report["status"] == "candidate_evidence_ready"


def test_cross_candidate_and_absolute_refs_block(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps({"candidate_id": "rc-old", "artifact_refs": ["C:/private/report.json"], "signoff": {"signed": False}}), encoding="utf-8")
    report = MODULE.verify_candidate(candidate, (evidence,))
    assert report["status"] == "candidate_evidence_blocked"
    assert "candidate_id_mismatch:evidence.json" in report["blockers"]
    assert "evidence_path_outside_root:evidence.json" in report["blockers"]
    assert "signoff_missing:evidence.json" in report["blockers"]


def test_missing_candidate_manifest_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(MODULE.CandidateEvidenceError, match="candidate_manifest_invalid"):
        MODULE.verify_candidate(tmp_path / "missing.json", ())
