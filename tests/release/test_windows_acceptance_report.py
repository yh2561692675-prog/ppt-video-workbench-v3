from __future__ import annotations

import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))


def test_report_passes_only_when_every_required_phase_passes() -> None:
    from scripts.windows_acceptance_report import REQUIRED_PHASES, build_report

    report = build_report(
        {
            "schema_version": "2.0",
            "release": {
                "candidate_id": "rc-abc1234-20260811T000000Z",
                "installer_sha256": "a" * 64,
            },
            "phases": {
                name: {
                    "result": "passed",
                    "started_at": "2026-08-11T00:00:00Z",
                    "finished_at": "2026-08-11T00:00:01Z",
                    "duration_ms": 1000,
                    "attempt": 1,
                    "reason_codes": [],
                    "evidence_refs": [],
                    "metrics": {},
                }
                for name in REQUIRED_PHASES
            },
        }
    )

    assert report["schema_version"] == "2.0"
    assert report["decision"] == "pass"
    assert report["blocking_failures"] == []


def test_report_blocks_and_redacts_user_paths_and_tokens() -> None:
    from scripts.windows_acceptance_report import build_report

    report = build_report(
        {
            "schema_version": "2.0",
            "token": "Bearer secret-value",
            "release": {
                "candidate_id": "rc-abc1234-20260811T000000Z",
                "installer_path": "C:\\Users\\HanYu\\setup.exe",
            },
            "phases": {},
        }
    )

    serialized = json.dumps(report)

    assert report["decision"] == "block"
    assert "first_launch" in report["blocking_failures"]
    assert "HanYu" not in serialized
    assert "secret-value" not in serialized


def test_write_report_accepts_utf8_bom_evidence_and_writes_manifest(tmp_path: Path) -> None:
    from scripts.windows_acceptance_report import REQUIRED_PHASES, write_report

    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "release": {
                    "candidate_id": "rc-abc1234-20260811T000000Z",
                    "installer_sha256": "a" * 64,
                },
                "phases": {
                    name: {
                        "result": "passed",
                        "started_at": "2026-08-11T00:00:00Z",
                        "finished_at": "2026-08-11T00:00:01Z",
                        "duration_ms": 1000,
                        "attempt": 1,
                        "reason_codes": [],
                        "evidence_refs": [],
                        "metrics": {},
                    }
                    for name in REQUIRED_PHASES
                },
            }
        ),
        encoding="utf-8-sig",
    )

    assert write_report(evidence_path, tmp_path / "report") == 0
    assert (tmp_path / "report" / "evidence-manifest.json").is_file()


def test_report_blocks_when_a_v2_phase_lacks_required_audit_fields() -> None:
    from scripts.windows_acceptance_report import REQUIRED_PHASES, build_report

    report = build_report(
        {
            "schema_version": "2.0",
            "release": {"candidate_id": "rc-abc1234-20260811T000000Z"},
            "phases": {name: {"result": "passed"} for name in REQUIRED_PHASES},
        }
    )

    assert report["decision"] == "block"
    assert "full_preflight" in report["blocking_failures"]


def test_report_blocks_when_referenced_evidence_is_missing(tmp_path: Path) -> None:
    from scripts.windows_acceptance_report import REQUIRED_PHASES, write_report

    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "release": {"candidate_id": "rc-abc1234-20260811T000000Z"},
                "phases": {
                    name: {
                        "result": "passed",
                        "started_at": "2026-08-11T00:00:00Z",
                        "finished_at": "2026-08-11T00:00:01Z",
                        "duration_ms": 1000,
                        "attempt": 1,
                        "reason_codes": [],
                        "evidence_refs": ["missing.json"] if name == "clean_install" else [],
                        "metrics": {},
                    }
                    for name in REQUIRED_PHASES
                },
            }
        ),
        encoding="utf-8",
    )

    assert write_report(evidence_path, tmp_path / "report") == 1


def test_install_scope_does_not_require_full_flow_phases() -> None:
    from scripts.windows_acceptance_report import INSTALL_PHASES, build_report

    report = build_report(
        {
            "schema_version": "2.0",
            "scope": "install",
            "release": {"candidate_id": "rc-abc1234-20260811T000000Z"},
            "phases": {
                name: {
                    "result": "passed",
                    "started_at": "2026-08-11T00:00:00Z",
                    "finished_at": "2026-08-11T00:00:01Z",
                    "duration_ms": 1000,
                    "attempt": 1,
                    "reason_codes": [],
                    "evidence_refs": [],
                    "metrics": {},
                }
                for name in INSTALL_PHASES
            },
        }
    )

    assert report["decision"] == "pass"
    assert report["blocking_failures"] == []
