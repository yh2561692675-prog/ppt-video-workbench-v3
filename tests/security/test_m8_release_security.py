from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_release_scripts_are_local_only_and_do_not_accept_auth_headers() -> None:
    sources = [
        ROOT / "scripts" / "launcher.ps1",
        ROOT / "scripts" / "doctor.ps1",
        ROOT / "tests" / "release" / "update-rollback.ps1",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in sources).lower()

    assert "0.0.0.0" not in combined
    assert "authorization:" not in combined
    assert "api_key" not in combined


def test_acceptance_documents_and_fixture_manifest_have_no_credential_residue() -> None:
    paths = [
        ROOT / "tests" / "acceptance" / "fixtures-manifest.json",
        ROOT / "tests" / "acceptance" / "acceptance-plan.md",
        ROOT / "docs" / "acceptance-report-RC1.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths if path.is_file())

    assert not re.search(r"\bsk-[a-z0-9]{12,}\b", combined, re.IGNORECASE)
    assert "bearer " not in combined.lower()
    assert "cookie:" not in combined.lower()
