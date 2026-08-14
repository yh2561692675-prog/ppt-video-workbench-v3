from __future__ import annotations

import json
from pathlib import Path

from scripts.personal_use_closure import aggregate_closure


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _candidate(tmp_path: Path, candidate_id: str = "rc-test") -> Path:
    return _write(
        tmp_path / "candidate.json",
        {
            "candidate_id": candidate_id,
            "status": "candidate_frozen",
            "source": {"git_commit": "a" * 40, "dirty": False},
        },
    )


def test_closure_passes_only_for_same_candidate_and_passed_stages(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    stage = _write(
        tmp_path / "g01.json",
        {
            "schema_version": "1.0",
            "stage": "G01",
            "candidate_id": "rc-test",
            "status": "passed",
            "blocking_failures": [],
            "evidence_refs": ["g01/log.json"],
        },
    )

    report = aggregate_closure(candidate, (stage,))

    assert report["status"] == "personal_use_ready"
    assert report["decision"] == "pass"


def test_closure_blocks_cross_candidate_evidence(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    stage = _write(
        tmp_path / "g02.json",
        {"candidate_id": "rc-other", "status": "passed", "evidence_refs": []},
    )

    report = aggregate_closure(candidate, (stage,))

    assert report["status"] == "personal_use_blocked"
    assert "candidate_id_mismatch:g02.json" in report["blocking_failures"]


def test_closure_blocks_a_candidate_identity_that_is_not_frozen(tmp_path: Path) -> None:
    candidate = _write(
        tmp_path / "candidate.json",
        {
            "candidate_id": "rc-test",
            "status": "candidate_blocked",
            "source": {"git_commit": "a" * 40, "dirty": False},
        },
    )
    stage = _write(
        tmp_path / "g03.json",
        {"candidate_id": "rc-test", "status": "passed", "evidence_refs": []},
    )

    report = aggregate_closure(candidate, (stage,))

    assert "candidate_not_frozen:candidate_blocked" in report["blocking_failures"]


def test_closure_blocks_missing_and_unsafe_evidence(tmp_path: Path) -> None:
    candidate = _candidate(tmp_path)
    stage = _write(
        tmp_path / "g03.json",
        {
            "candidate_id": "rc-test",
            "status": "blocked",
            "blocking_failures": ["windows_missing"],
            "evidence_refs": ["..\\outside.json"],
        },
    )

    report = aggregate_closure(candidate, (stage,))

    assert report["status"] == "personal_use_blocked"
    assert "stage_not_passed:g03.json" in report["blocking_failures"]
    assert "evidence_path_outside_root:g03.json" in report["blocking_failures"]
