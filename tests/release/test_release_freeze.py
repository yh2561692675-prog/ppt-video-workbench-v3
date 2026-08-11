from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]
MANIFEST = ROOT / "tests" / "acceptance" / "results" / "RC1" / "evidence-manifest.json"
FREEZE_SCRIPT = ROOT / "scripts" / "freeze-release.ps1"


def test_release_signoff_template_blocks_v1_until_rc1_is_signed() -> None:
    signoff = (ROOT / "docs" / "acceptance-signoff-v1.0.md").read_text(encoding="utf-8")
    release_notes = (ROOT / "docs" / "release-notes-v1.0.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    evidence = json.loads(MANIFEST.read_text(encoding="utf-8"))

    assert "blocked_pending_manual_signoff" in signoff
    assert "pending_manual_windows" in signoff
    assert "v1.0.0" in release_notes
    assert "pending_manual_windows" in release_notes
    assert "M8 RC1" in changelog
    assert evidence["status"] == "pending_manual_windows"
    assert evidence["signoff"]["signed"] is False


def test_freeze_script_requires_signed_rc1_and_blocks_current_evidence() -> None:
    script = FREEZE_SCRIPT.read_text(encoding="utf-8")

    assert "pending_manual_windows" in script
    assert '"signed"' in script
    assert '"P0"' in script
    assert '"P1"' in script
    assert "v1.0.0" in script
    assert "Mandatory = $true" in script
    assert 'schema_version -ne "2.0"' in script
    assert "physical_windows" in script
    assert "ReleaseArtifactManifest" in script
    assert "full_preflight" in script
    assert "AddDays(-7)" in script
    assert "git tag" not in script.lower()
