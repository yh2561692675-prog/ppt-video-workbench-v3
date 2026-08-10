from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
REPORT = ROOT / "docs" / "acceptance-report-RC1.md"
MANIFEST = ROOT / "tests" / "acceptance" / "results" / "RC1" / "evidence-manifest.json"


def test_rc1_report_is_explicitly_pending_manual_windows_signoff() -> None:
    report = REPORT.read_text(encoding="utf-8")
    evidence = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert "pending_manual_windows" in report
    assert evidence["status"] == "pending_manual_windows"
    assert evidence["signoff"]["signed"] is False
    assert evidence["defects"]["P0"] == "not_assessed"
    assert evidence["defects"]["P1"] == "not_assessed"
    assert evidence["defects"]["P2"] == "not_assessed"


def test_rc1_manifest_lists_the_complete_package_and_required_scenarios() -> None:
    evidence = json.loads(MANIFEST.read_text(encoding="utf-8"))
    artifact_names = {item["name"] for item in evidence["artifacts"]}
    scenario_ids = {item["id"] for item in evidence["scenarios"]}

    assert {
        "MP4",
        "SRT",
        "旁白 DOCX",
        "分页音频",
        "Remotion 工程",
        "配置",
        "预检报告",
        "日志",
        "SHA-256 清单",
    } <= artifact_names
    assert {
        "RC-LOCAL",
        "RC-SCAN",
        "RC-IMAGES",
        "RC-HEYGEN",
        "RC-RECOVERY",
        "RC-AUDIOVISUAL",
    } <= scenario_ids
    assert all(item["result"] == "pending_manual_windows" for item in evidence["scenarios"])
