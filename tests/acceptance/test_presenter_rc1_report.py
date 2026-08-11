import json
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_presenter_release_stays_internal_until_manual_windows_evidence_exists() -> None:
    manifest = json.loads((ROOT / "installer/runtime-manifest.json").read_text(encoding="utf-8"))
    report = (ROOT / "docs/presenter-mode-acceptance-report-RC1.md").read_text(encoding="utf-8")

    assert manifest["feature_flags"]["presenter_mode"] == "internal"
    assert "Status: **pending_manual_windows**" in report
    assert "stable_optional" in report


def test_presenter_manual_plan_requires_every_delivery_artifact_and_threshold() -> None:
    plan = (ROOT / "tests/acceptance/presenter-mode-plan.md").read_text(encoding="utf-8")

    for artifact in (
        "MP4",
        "SRT",
        "transcript JSON",
        "page matches/anchors",
        "presenter window plan",
        "preflight report",
        "logs",
        "timeline hash",
    ):
        assert artifact in plan
    for threshold in ("80 ms", "150 ms", "250 ms"):
        assert threshold in plan


def test_presenter_windows_script_cannot_claim_automatic_manual_acceptance() -> None:
    script = (ROOT / "scripts/presenter-windows-acceptance.ps1").read_text(encoding="ascii")

    assert "PLAN_ONLY" in script
    assert "ConfirmManualAcceptance" in script
    assert "cannot claim" in script
