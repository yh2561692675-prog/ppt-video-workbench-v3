from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts" / "validate-release.py"


def _write_project(root: Path, *, version: str = "0.1.0", notes: bool = True) -> None:
    for path in (root / "pyproject.toml", root / "apps/api/pyproject.toml"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'[project]\nname = "fixture"\nversion = "{version}"\n', encoding="utf-8")
    for path in (root / "package.json", root / "apps/web/package.json"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": version}), encoding="utf-8")
    if notes:
        release_notes = root / "docs/releases" / f"v{version}.md"
        release_notes.parent.mkdir(parents=True, exist_ok=True)
        release_notes.write_text("# Fixture release\n", encoding="utf-8")


def _run(root: Path, version: str = "0.1.0") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--version", version],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def test_release_validation_accepts_aligned_versions_and_notes(tmp_path: Path) -> None:
    _write_project(tmp_path)

    result = _run(tmp_path)

    assert result.returncode == 0
    assert "validated release v0.1.0" in result.stdout


def test_release_validation_rejects_version_drift(tmp_path: Path) -> None:
    _write_project(tmp_path)
    (tmp_path / "apps/web/package.json").write_text(
        json.dumps({"version": "0.2.0"}), encoding="utf-8"
    )

    result = _run(tmp_path)

    assert result.returncode != 0
    assert "apps/web/package.json=0.2.0" in result.stderr


def test_release_validation_rejects_missing_notes(tmp_path: Path) -> None:
    _write_project(tmp_path, notes=False)

    result = _run(tmp_path)

    assert result.returncode != 0
    assert "release notes are missing or empty" in result.stderr
