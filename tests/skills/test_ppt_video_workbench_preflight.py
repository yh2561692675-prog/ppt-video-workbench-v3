from __future__ import annotations

import json
import shutil
import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).parents[2]
SCRIPT = ROOT / "skills" / "ppt-video-workbench" / "scripts" / "preflight.py"
SKILL_ROOT = SCRIPT.parents[1]
SPEC = spec_from_file_location("ppt_video_workbench_preflight", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
PREFLIGHT = module_from_spec(SPEC)
sys.modules[SPEC.name] = PREFLIGHT
SPEC.loader.exec_module(PREFLIGHT)


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


def run_preflight(
    repo: Path, *, script: Path = SCRIPT, capability: str | None = None
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, str(script), "--repo", str(repo), "--json"]
    if capability is not None:
        command.extend(["--capability", capability])
    return subprocess.run(
        command,
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


def test_capability_contract_blocks_only_selected_missing_tools() -> None:
    checks = [
        PREFLIGHT.Check(name, "ok", "available")
        for name in (*PREFLIGHT.REQUIRED_FILES, *PREFLIGHT.TOOLS)
    ]
    checks = [
        PREFLIGHT.Check(check.name, "missing", "not found")
        if check.name in {"ffmpeg", "ffprobe", "soffice"}
        else check
        for check in checks
    ]

    source_blockers = PREFLIGHT.blocking_checks(checks, "source")
    render_blockers = PREFLIGHT.blocking_checks(checks, "render")
    office_blockers = PREFLIGHT.blocking_checks(checks, "office-import")

    assert source_blockers == []
    assert {check.name for check in render_blockers} == {"ffmpeg", "ffprobe"}
    assert {check.name for check in office_blockers} == {"soffice"}


def test_installed_copy_validates_external_repository(tmp_path: Path) -> None:
    installed_skill = tmp_path / "installed" / "ppt-video-workbench"
    shutil.copytree(SKILL_ROOT, installed_skill)

    result = run_preflight(
        ROOT,
        script=installed_skill / "scripts" / "preflight.py",
        capability="source",
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["capability"] == "source"
    assert payload["ready"] is True
