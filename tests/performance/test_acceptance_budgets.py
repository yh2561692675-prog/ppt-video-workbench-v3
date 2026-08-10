from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_standard_project_is_the_eight_page_performance_baseline() -> None:
    manifest = json.loads(
        (ROOT / "examples" / "demo-project" / "project.json").read_text(encoding="utf-8")
    )

    assert len(manifest["pages"]) == 8
    assert manifest["current_step"] == 1


def test_release_budget_declares_expected_complete_package() -> None:
    manifest = json.loads(
        (ROOT / "tests" / "acceptance" / "fixtures-manifest.json").read_text(encoding="utf-8")
    )
    outputs = set(manifest["standard_project"]["expected_outputs"])

    assert {"MP4", "SRT", "旁白 DOCX", "分页音频", "Remotion 工程"} <= outputs
    assert manifest["standard_project"]["content_policy"].startswith("synthetic_only")
