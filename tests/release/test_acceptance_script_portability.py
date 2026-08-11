from __future__ import annotations

import json
from pathlib import Path, PureWindowsPath

REPOSITORY_ROOT = Path(__file__).parents[2]


def _source(relative_path: str) -> str:
    return (REPOSITORY_ROOT / relative_path).read_text(encoding="utf-8")


def test_effect_acceptance_requires_an_operator_supplied_reference() -> None:
    source = _source("scripts/effect-engine-windows-acceptance.ps1")

    assert '[string]$ProjectRoot = ""' in source
    assert '[string]$ReferenceVideo = ""' in source
    assert "$PSScriptRoot" in source
    assert "xwechat_files" not in source
    assert "F:\\ppt-video-workbench-v3" not in source


def test_presenter_acceptance_resolves_the_repository_from_its_script() -> None:
    source = _source("scripts/presenter-windows-acceptance.ps1")

    assert '[string]$ProjectRoot = ""' in source
    assert "$PSScriptRoot" in source
    assert "F:\\ppt-video-workbench-v3" not in source


def test_quality_gate_and_visual_fixture_are_checkout_portable() -> None:
    source = _source("scripts/run-video-quality-gates.ps1")
    fixture = json.loads(
        (REPOSITORY_ROOT / "tests/visual/effects/chapter-curtain.json").read_text(
            encoding="utf-8"
        )
    )

    assert "$PSScriptRoot" in source
    assert "F:\\ppt-video-workbench-v3" not in source
    reference_path = fixture["reference_video"]["path"]
    assert not PureWindowsPath(reference_path).is_absolute()
    assert "xwechat_files" not in reference_path
