from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "skills" / "ppt-video-workbench" / "scripts" / "preflight.py"
SKILL_ROOT = SCRIPT.parents[1]


def test_skill_layout_contract() -> None:
    required = {
        "SKILL.md",
        "agents/openai.yaml",
        "scripts/preflight.py",
        "references/source-workflow.md",
        "references/troubleshooting.md",
        "references/maintenance.md",
    }

    assert all((SKILL_ROOT / relative).is_file() for relative in required)
    skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    metadata = (SKILL_ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
    assert skill.startswith("---\nname: ppt-video-workbench\n")
    assert "$ppt-video-workbench" in metadata
    assert not (SKILL_ROOT / "README.md").exists()


def run_preflight(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo), "--json"],
        check=False,
        capture_output=True,
        text=True,
    )


def test_preflight_accepts_repository_root() -> None:
    result = run_preflight(ROOT)

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ready"] is True
    assert all(check["status"] != "missing" for check in payload["checks"])


def test_preflight_rejects_unrelated_directory(tmp_path: Path) -> None:
    result = run_preflight(tmp_path)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["ready"] is False
    missing = {check["name"] for check in payload["checks"] if check["status"] == "missing"}
    assert "pyproject.toml" in missing
    assert "pnpm-workspace.yaml" in missing
