from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from workbench.domain.models import ProjectManifest
from workbench.main import create_app
from workbench.preflight.checks.runtime import check_runtime
from workbench.preflight.engine import PreflightEngine


def _project() -> ProjectManifest:
    now = datetime.now(UTC)
    return ProjectManifest(
        id=uuid4(),
        name="运行时检查",
        project_dir="runtime-check",
        created_at=now,
        updated_at=now,
    )


def test_legacy_manifest_without_m6_fields_remains_valid(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    payload = {
        "schema_version": 1,
        "id": str(uuid4()),
        "name": "旧项目",
        "project_dir": "旧项目",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "pages": [],
    }

    manifest = ProjectManifest.model_validate(payload)

    assert manifest.preflight_report is None
    assert manifest.preflight_history == []
    assert manifest.issue_confirmations == []


def test_runtime_check_instructs_user_to_restore_packaged_runtime(tmp_path: Path) -> None:
    _, issues = check_runtime(
        _project(),
        tmp_path,
        {"python": "3.12", "node": "node.exe", "ffmpeg": "ffmpeg.exe", "ffprobe": ""},
    )

    assert len(issues) == 1
    assert issues[0].code == "runtime_component_missing"
    assert "prepare-runtime.ps1" in issues[0].action


def test_app_uses_bundled_ffmpeg_for_video_export(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / "runtime"
    for relative_path in (
        "node/node.exe",
        "remotion/node_modules/@remotion/cli/remotion-cli.js",
        "remotion/src/index.ts",
        "ffmpeg/ffmpeg.exe",
        "ffmpeg/ffprobe.exe",
    ):
        path = runtime / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative_path, encoding="utf-8")
    monkeypatch.setenv("WORKBENCH_RUNTIME_ROOT", str(runtime))

    app = create_app(tmp_path)

    assert app.state.video_export_service.ffmpeg == str(runtime / "ffmpeg/ffmpeg.exe")
    assert app.state.video_export_service.ffprobe == str(runtime / "ffmpeg/ffprobe.exe")


def test_development_runtime_probe_uses_local_tools_without_bundled_runtime(
    monkeypatch,
) -> None:
    monkeypatch.delenv("WORKBENCH_RUNTIME_ROOT", raising=False)
    monkeypatch.setattr(
        "workbench.preflight.engine.shutil.which",
        lambda command: f"/tools/{command}",
    )

    probe = PreflightEngine._default_runtime_probe()

    assert probe["node"] == "/tools/node"
    assert probe["ffmpeg"] == "/tools/ffmpeg"
    assert probe["ffprobe"] == "/tools/ffprobe"
