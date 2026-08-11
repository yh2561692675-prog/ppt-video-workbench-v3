from __future__ import annotations

import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]
PLATFORM_ROOT = REPOSITORY_ROOT / "peripheral-platform"


def test_s1_runtime_manifest_declares_every_module_and_render_dependency() -> None:
    manifest = json.loads(
        (PLATFORM_ROOT / "packaging" / "runtime-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["bundled_modules"] == [f"P{index:02d}" for index in range(3, 13)]
    assert set(manifest["required_release_files"]) == {
        "runtime/ffmpeg/ffmpeg.exe",
        "runtime/ffmpeg/ffprobe.exe",
        "runtime/remotion/node_modules/@remotion/cli/remotion-cli.js",
        "runtime/remotion/src/index.ts",
    }
    assert "peripheral/scripts/verify-s1.ps1" in manifest["required_files"]


def test_pyinstaller_spec_bundles_all_s1_entrypoints() -> None:
    source = (PLATFORM_ROOT / "packaging" / "peripheral-host.spec").read_text(encoding="utf-8")

    assert 'apps" / "api" / "src' in source
    for index in range(3, 13):
        assert f"workbench.business_modules.p{index:02d}_" in source


def test_launcher_passes_render_tools_and_degrades_safely() -> None:
    source = (REPOSITORY_ROOT / "scripts" / "launcher.ps1").read_text(encoding="ascii")

    assert "WORKBENCH_FFMPEG" in source
    assert "WORKBENCH_FFPROBE" in source
    assert 'PERIPHERAL_DEGRADED = "true"' in source
    assert "main workflow will continue" in source


def test_s1_verifier_has_non_forgeable_manual_acceptance_gate() -> None:
    source = (PLATFORM_ROOT / "scripts" / "verify-s1.ps1").read_text(encoding="ascii")

    for marker in ("S1_AUTOMATION", "S1_WINDOWS", "S1_ACCEPTANCE"):
        assert f'{marker}=" + $(if (' in source
    assert "S1_ACCEPTANCE_EVIDENCE" in source
    assert "real_heygen" in source
    assert "manual_av_signoff" in source
    assert "Remove-Item" not in source
