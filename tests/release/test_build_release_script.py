import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from uuid import uuid4

import pytest


def test_build_release_script_is_ascii_only_for_windows_powershell() -> None:
    """Avoid Windows PowerShell parsing failures caused by transferred UTF-8 scripts."""
    script_path = Path(__file__).parents[2] / "scripts" / "build-release.ps1"

    script_path.read_bytes().decode("ascii")


def test_build_release_refuses_to_compile_an_installer_without_all_runtime_payloads() -> None:
    """A missing API executable must stop the build before Inno Setup runs."""
    script_path = Path(__file__).parents[2] / "scripts" / "build-release.ps1"
    source = script_path.read_text(encoding="ascii")

    assert "function Assert-RequiredReleaseFile" in source
    assert '"api\\workbench.exe"' in source
    assert '"web\\index.html"' in source
    assert '"runtime-manifest.json"' in source
    assert '"runtime\\node\\node.exe"' in source
    assert '"runtime\\ffmpeg\\ffmpeg.exe"' in source
    assert '"runtime\\ffmpeg\\ffprobe.exe"' in source
    assert "PyInstaller did not produce the API runtime" in source
    assert source.index("PyInstaller did not produce the API runtime") < source.index("& $isccPath")


def test_build_release_validates_ffprobe_identity_before_installer() -> None:
    """A renamed FFmpeg binary must never be accepted as the FFprobe runtime."""
    script_path = Path(__file__).parents[2] / "scripts" / "build-release.ps1"
    source = script_path.read_text(encoding="ascii")

    assert "function Assert-ExecutableIdentity" in source
    assert (
        'Assert-ExecutableIdentity -Path (Join-Path $stageRoot "runtime\\ffmpeg\\ffprobe.exe") '
        '-ExpectedName "ffprobe"'
    ) in source


def test_build_release_requires_quality_filter_capabilities_before_installer() -> None:
    """A minimal FFmpeg binary must not enter the release payload."""
    script_path = Path(__file__).parents[2] / "scripts" / "build-release.ps1"
    source = script_path.read_text(encoding="ascii")

    assert "function Assert-QualityFilterCapabilities" in source
    for filter_name in (
        "blackdetect",
        "freezedetect",
        "ebur128",
        "silencedetect",
        "select",
        "showinfo",
    ):
        assert f'"{filter_name}"' in source
    assert source.count("Assert-QualityFilterCapabilities -Executable") >= 2


def test_prepare_runtime_requires_quality_filter_capabilities_before_staging() -> None:
    """Runtime staging must reject FFmpeg builds without quality analyzers."""
    script_path = Path(__file__).parents[2] / "scripts" / "prepare-runtime.ps1"
    source = script_path.read_text(encoding="ascii")

    assert "function Assert-QualityFilterCapabilities" in source
    assert "Assert-QualityFilterCapabilities -Executable $ffmpeg" in source
    for filter_name in (
        "blackdetect",
        "freezedetect",
        "ebur128",
        "silencedetect",
        "select",
        "showinfo",
    ):
        assert f'"{filter_name}"' in source


def test_build_release_requires_python_and_vc_runtime_dlls_in_api_payload() -> None:
    """The installer must not ship an API executable with an unloadable Python DLL."""
    script_path = Path(__file__).parents[2] / "scripts" / "build-release.ps1"
    source = script_path.read_text(encoding="ascii")

    for relative_path in (
        "api\\_internal\\python312.dll",
        "api\\_internal\\vcruntime140.dll",
        "api\\_internal\\vcruntime140_1.dll",
        "api\\_internal\\msvcp140.dll",
    ):
        assert relative_path in source


def test_build_release_promotes_the_pyinstaller_onedir_bundle_before_payload_gates() -> None:
    """The nested PyInstaller bundle must be promoted to release/api before validation."""
    script_path = Path(__file__).parents[2] / "scripts" / "build-release.ps1"
    source = script_path.read_text(encoding="ascii")

    assert '"scripts/stage_pyinstaller_onedir.py"' in source
    assert "uv run --frozen python $stagePyInstallerBundle" in source
    assert "--source $pyInstallerBundleRoot" in source
    assert "--destination $apiRoot" in source
    stage_index = source.index("uv run --frozen python $stagePyInstallerBundle")
    assert (
        source.index("Assert-RequiredApiRuntime -StageRoot $stageRoot", stage_index) > stage_index
    )


def test_build_release_isolates_pyinstaller_work_per_staging_root() -> None:
    """Concurrent release builds must not delete each other's PyInstaller work tree."""
    script_path = Path(__file__).parents[2] / "scripts" / "build-release.ps1"
    source = script_path.read_text(encoding="ascii")

    assert '$pyInstallerWorkRoot = Join-Path $stageRoot "_pyinstaller-work"' in source
    assert "--workpath $pyInstallerWorkRoot" in source
    assert 'Join-Path $repoRoot "dist/pyinstaller-work"' not in source


def test_build_release_stops_when_inno_setup_compilation_fails() -> None:
    """An Inno error must not be reported as a stale installer success."""
    script_path = Path(__file__).parents[2] / "scripts" / "build-release.ps1"
    source = script_path.read_text(encoding="ascii")

    assert "$isccExitCode = $LASTEXITCODE" in source
    assert "Inno Setup compiler failed with exit code" in source
    assert "if ($isccExitCode -ne 0)" in source
    assert source.index("if ($isccExitCode -ne 0)") < source.index(
        "Test-Path -LiteralPath $installerPath"
    )


def test_pyinstaller_spec_resolves_the_repository_root_from_its_own_directory() -> None:
    """The release spec must not resolve desktop.py from the parent workspace."""
    spec_path = Path(__file__).parents[2] / "apps" / "api" / "workbench.spec"
    source = spec_path.read_text(encoding="utf-8")

    assert "project_root = Path(SPECPATH).parents[1]" in source


def test_pyinstaller_spec_bundles_visual_cpp_runtime_dlls_for_clean_windows_hosts() -> None:
    """The frozen API must load without a machine-wide VC++ redistributable."""
    spec_path = Path(__file__).parents[2] / "apps" / "api" / "workbench.spec"
    source = spec_path.read_text(encoding="utf-8")

    for runtime_dll in (
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "msvcp140.dll",
    ):
        assert runtime_dll in source
    assert "binaries" in source
    assert "Visual C++ runtime DLLs" in source


def test_prepare_runtime_discovers_pnpm_when_no_explicit_path_is_supplied() -> None:
    script_path = Path(__file__).parents[2] / "scripts" / "prepare-runtime.ps1"
    source = script_path.read_text(encoding="ascii")

    assert '[string]$PnpmExecutable = "pnpm"' not in source
    assert '-CommandName "pnpm.cmd"' in source


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell runtime staging is Windows-only")
def test_prepare_runtime_rejects_ffmpeg_renamed_as_ffprobe() -> None:
    """A mislabeled ffmpeg binary must not be staged as the FFprobe runtime."""
    repository_root = Path(__file__).parents[2]
    ffmpeg = shutil.which("ffmpeg")
    powershell = shutil.which("powershell.exe")
    assert ffmpeg is not None
    assert powershell is not None
    output_relative = f".tmp-tests/runtime-{uuid4()}"
    output = repository_root / output_relative

    try:
        completed = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(repository_root / "scripts" / "prepare-runtime.ps1"),
                "-Output",
                output_relative,
                "-NodeExecutable",
                sys.executable,
                "-FfmpegExecutable",
                ffmpeg,
                "-FfprobeExecutable",
                ffmpeg,
                "-PnpmExecutable",
                sys.executable,
            ],
            cwd=repository_root,
            check=False,
            capture_output=True,
            text=True,
        )
        diagnostics = completed.stdout + completed.stderr
        assert completed.returncode != 0
        assert "FfprobeExecutable is not an ffprobe executable" in diagnostics
        assert not output.exists()
    finally:
        shutil.rmtree(output, ignore_errors=True)


def test_prepare_runtime_uses_modern_hoisted_pnpm_deploy_for_windows() -> None:
    """Modern pnpm deployment avoids the deep package directories of legacy deploy."""
    script_path = Path(__file__).parents[2] / "scripts" / "prepare-runtime.ps1"
    source = script_path.read_text(encoding="ascii")

    assert "--config.node-linker=hoisted" in source
    assert "--config.inject-workspace-packages=true" in source
    assert "deploy --prod --legacy" not in source


def test_prepare_runtime_deploys_a_flat_node_modules_tree_for_windows_installers() -> None:
    """The packaged renderer must not carry pnpm's deep virtual store into Inno Setup."""
    script_path = Path(__file__).parents[2] / "scripts" / "prepare-runtime.ps1"
    source = script_path.read_text(encoding="ascii")

    assert 'Join-Path $remotionRuntime "node_modules\\.pnpm"' in source
    assert "Get-ChildItem -LiteralPath $pnpmVirtualStore -Directory" in source
    assert "virtual package directories" in source


def test_prepare_runtime_stages_required_executables_at_the_manifest_paths() -> None:
    """The prepared tree must contain the exact executable names consumed by the installer."""
    script_path = Path(__file__).parents[2] / "scripts" / "prepare-runtime.ps1"
    source = script_path.read_text(encoding="ascii")

    assert "function Stage-Executable" in source
    expected_executables = {
        "$node": "node\\node.exe",
        "$ffmpeg": "ffmpeg\\ffmpeg.exe",
        "$ffprobe": "ffmpeg\\ffprobe.exe",
    }
    for source_executable, destination in expected_executables.items():
        command = (
            f"Stage-Executable -SourceExecutable {source_executable} "
            f'-Destination (Join-Path $runtimeRoot "{destination}")'
        )
        assert command in source


def test_prepare_runtime_never_recursively_copies_an_executable_parent_directory() -> None:
    """A tool installed at a drive root must not cause protected sibling folders to be copied."""
    script_path = Path(__file__).parents[2] / "scripts" / "prepare-runtime.ps1"
    source = script_path.read_text(encoding="ascii")

    assert "Get-ChildItem -LiteralPath $sourceDirectory" not in source
    assert "Copy-Item -LiteralPath $SourceExecutable -Destination $Destination -Force" in source


def test_prepare_runtime_requires_the_actual_remotion_cli_entrypoint() -> None:
    """The locked Remotion 4 package exposes remotion-cli.js at package root."""
    script_path = Path(__file__).parents[2] / "scripts" / "prepare-runtime.ps1"
    source = script_path.read_text(encoding="ascii")

    assert "remotion\\node_modules\\@remotion\\cli\\remotion-cli.js" in source


def test_build_release_copies_prepared_runtime_with_a_wildcard_aware_path() -> None:
    """PowerShell's LiteralPath treats '*' as text and cannot copy runtime-assets content."""
    script_path = Path(__file__).parents[2] / "scripts" / "build-release.ps1"
    source = script_path.read_text(encoding="ascii")

    assert 'Copy-Item -Path (Join-Path $SourceRoot "*")' in source
    assert 'Copy-Item -LiteralPath (Join-Path $SourceRoot "*")' not in source


def test_source_update_archive_includes_the_inno_setup_script(tmp_path: Path) -> None:
    """A Windows update archive must include the installer source used by the build script."""
    repository_root = Path(__file__).parents[2]
    archive_path = tmp_path / "source-update.zip"

    subprocess.run(
        [
            sys.executable,
            str(repository_root / "scripts" / "package-source-update.py"),
            "--output",
            str(archive_path),
        ],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    )

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())

    assert "installer/workbench.iss" in names
    assert "scripts/build-release.ps1" in names
    assert "runtime-assets/node/node.exe" not in names
    assert not any(name.startswith(("backup/", "cache/", "workspace-data/")) for name in names)


def test_installer_uses_an_overridable_short_release_payload_root() -> None:
    """Inno Setup must expand the mapped payload path instead of treating it as text."""
    repository_root = Path(__file__).parents[2]
    installer_source = (repository_root / "installer" / "workbench.iss").read_text(encoding="utf-8")
    build_source = (repository_root / "scripts" / "build-release.ps1").read_text(encoding="ascii")

    assert "#ifdef ReleasePayload" in installer_source
    assert "#define ReleaseRoot ReleasePayload" in installer_source
    assert '#define ReleaseRoot "{#ReleasePayload}"' not in installer_source
    assert 'Source: "{#ReleaseRoot}\\*"' in installer_source
    assert "subst $releasePayloadDrive $stageRoot" in build_source
    assert '"/DReleasePayload=$releasePayloadDrive"' in build_source
    assert "subst $releasePayloadDrive /D" in build_source


def test_release_freeze_requires_a_passing_p01_report_when_one_is_supplied() -> None:
    repository_root = Path(__file__).parents[2]
    source = (repository_root / "scripts" / "freeze-release.ps1").read_text(encoding="utf-8")

    assert "WindowsAcceptanceReport" in source
    assert 'decision -ne "pass"' in source
    assert "P01 Windows acceptance is not passed" in source


def test_build_release_writes_and_verifies_the_artifact_manifest() -> None:
    repository_root = Path(__file__).parents[2]
    source = (repository_root / "scripts" / "build-release.ps1").read_text(encoding="ascii")

    assert 'Join-Path $repoRoot "scripts/release_artifacts.py"' in source
    assert 'Join-Path $installerOutputRoot "release-artifacts.json"' in source
    assert "--output $artifactManifestPath" in source
    assert "--verify $artifactManifestPath" in source
    assert "WINDOWS_RELEASE_BUILD=PASS" in source


def test_build_release_uses_frozen_python_environment_and_source_integrity_guards() -> None:
    repository_root = Path(__file__).parents[2]
    source = (repository_root / "scripts" / "build-release.ps1").read_text(encoding="ascii")

    assert "uv sync --frozen" in source
    assert "uv run --frozen --with \"pyinstaller==6.16.0\"" in source
    assert "uv run --frozen python" in source
    assert "Get-SourceIntegrity" in source
    assert "SOURCE_INTEGRITY_BEFORE=" in source
    assert "SOURCE_INTEGRITY_FINAL=" in source
    assert "uv_lock_sha256" in source
    assert "Source HEAD changed during release build" in source
    assert "uv.lock changed during release build" in source


def test_build_release_packages_the_no_console_desktop_launcher() -> None:
    repository_root = Path(__file__).parents[2]
    source = (repository_root / "scripts" / "build-release.ps1").read_text(encoding="ascii")

    assert 'Join-Path $repoRoot "apps/api/workbench-launcher.spec"' in source
    assert 'Join-Path $stageRoot "launcher"' in source
    assert '"launcher\\workbench-launcher.exe"' in source
