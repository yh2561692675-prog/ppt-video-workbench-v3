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
            "release": {"installer_sha256": "a" * 64},
            "phases": {name: {"result": "passed"} for name in REQUIRED_PHASES},
        }
    )

    assert report["decision"] == "pass"
    assert report["blocking_failures"] == []


def test_report_blocks_and_redacts_user_paths_and_tokens() -> None:
    from scripts.windows_acceptance_report import build_report

    report = build_report(
        {
            "token": "Bearer secret-value",
            "release": {"installer_path": "C:\\Users\\HanYu\\setup.exe"},
            "phases": {},
        }
    )

    serialized = json.dumps(report)

    assert report["decision"] == "block"
    assert "first_launch" in report["blocking_failures"]
    assert "HanYu" not in serialized
    assert "secret-value" not in serialized


def test_write_report_accepts_utf8_bom_evidence_from_powershell(tmp_path: Path) -> None:
    from scripts.windows_acceptance_report import REQUIRED_PHASES, write_report

    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        json.dumps({"phases": {name: {"result": "passed"} for name in REQUIRED_PHASES}}),
        encoding="utf-8-sig",
    )

    assert write_report(evidence_path, tmp_path / "report") == 0
