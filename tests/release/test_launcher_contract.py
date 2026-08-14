from __future__ import annotations

from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]
LAUNCHER = REPOSITORY_ROOT / "scripts" / "launcher.ps1"
INSTALLER = REPOSITORY_ROOT / "installer" / "workbench.iss"
SMOKE_SCRIPT = REPOSITORY_ROOT / "tests" / "release" / "install-smoke.ps1"


def test_launcher_defaults_to_user_workspace_data() -> None:
    source = LAUNCHER.read_text(encoding="ascii")

    assert 'Join-Path $stateRoot "workspace-data"' in source
    workspace_block = source.split("$workspaceRoot =", 1)[1].split("$cacheRoot", 1)[0]
    assert '"F:\\Video"' not in workspace_block


def test_launcher_is_local_only_and_waits_for_health() -> None:
    source = LAUNCHER.read_text(encoding="utf-8")

    assert "127.0.0.1" in source
    assert "/api/health" in source
    assert "TcpListener" in source
    assert "CreateNew" in source
    assert "Start-Process" in source
    assert "WORKBENCH_WEB_ROOT" in source
    assert "WORKBENCH_RUNTIME_ROOT" in source
    assert "index.html" in source
    assert "endpoint.json" in source
    assert "0.0.0.0" not in source
    assert "api_key" not in source.lower()
    assert "authorization" not in source.lower()


def test_launcher_supports_an_isolated_state_root_for_windows_acceptance() -> None:
    """P01 must not collide with a user's already-running Workbench instance."""
    launcher_source = LAUNCHER.read_text(encoding="utf-8")
    runner = REPOSITORY_ROOT / "tests" / "release" / "windows-acceptance.ps1"
    runner_source = runner.read_text(encoding="utf-8")

    assert "WORKBENCH_STATE_ROOT" in launcher_source
    assert "WORKBENCH_STATE_ROOT" in runner_source
    assert "$stateRoot" in runner_source


def test_launcher_is_ascii_only_for_windows_powershell() -> None:
    LAUNCHER.read_bytes().decode("ascii")


def test_inno_setup_is_non_admin_and_preserves_user_data() -> None:
    source = INSTALLER.read_text(encoding="utf-8")

    assert "PrivilegesRequired=lowest" in source
    assert "OutputBaseFilename" in source
    assert "{autoprograms}" in source
    assert "{autodesktop}" in source
    assert "workbench-launcher.exe" in source
    assert "WindowsPowerShell" not in source
    assert "workspace-data" in source
    assert "{localappdata}" in source
    assert "UninstallDelete" in source
    assert "workspace-data" not in source.split("[UninstallDelete]", 1)[1]
    assert "[UninstallRun]" in source
    assert "shutdown" in source


def test_install_smoke_covers_windows_installation_matrix() -> None:
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")

    for marker in (
        "/VERYSILENT",
        "/SILENT",
        "中文",
        "Get-Process",
        "workspace-data",
        "unins000.exe",
    ):
        assert marker in source


def test_windows_acceptance_runner_proves_install_start_and_retention() -> None:
    runner = REPOSITORY_ROOT / "tests" / "release" / "windows-acceptance.ps1"
    source = runner.read_text(encoding="utf-8")

    for required in (
        "Get-FileHash",
        "-Algorithm SHA256",
        "Start-Process",
        "instance.json",
        "first_launch",
        "workspace_retention",
        "P01_WINDOWS_ACCEPTANCE=PASS",
        "P01_WINDOWS_ACCEPTANCE=BLOCK",
        "ArtifactManifest",
        "release_artifacts.py",
    ):
        assert required in source
    assert "Remove-Item -LiteralPath $workspaceRoot" not in source


def test_windows_acceptance_preserves_inno_setup_log_on_install_failure() -> None:
    """An installer failure must leave the Inno Setup diagnostic log discoverable."""
    runner = REPOSITORY_ROOT / "tests" / "release" / "windows-acceptance.ps1"
    source = runner.read_text(encoding="utf-8")

    assert "installer.log" in source
    assert "/LOG=" in source


def test_windows_acceptance_captures_first_launch_diagnostics() -> None:
    """A startup timeout must leave the launcher and API failure evidence behind."""
    runner = REPOSITORY_ROOT / "tests" / "release" / "windows-acceptance.ps1"
    launcher_source = LAUNCHER.read_text(encoding="utf-8")
    runner_source = runner.read_text(encoding="utf-8")

    assert "WORKBENCH_LOG_ROOT" in runner_source
    assert "RedirectStandardOutput" in runner_source
    assert "RedirectStandardError" in runner_source
    assert "WORKBENCH_LOG_ROOT" in launcher_source
    assert "RedirectStandardOutput" in launcher_source
    assert "RedirectStandardError" in launcher_source
    assert "API process exited" in launcher_source


def test_windows_acceptance_stops_the_owned_api_before_waiting_for_launcher_cleanup() -> None:
    """Healthy launch phases must let launcher.ps1 run its finally cleanup."""
    runner = REPOSITORY_ROOT / "tests" / "release" / "windows-acceptance.ps1"
    launcher_source = LAUNCHER.read_text(encoding="utf-8")
    runner_source = runner.read_text(encoding="utf-8")
    stop_function = runner_source.split("function Stop-OwnedLauncher", 1)[1].split(
        "function Wait-HealthyEndpoint", 1
    )[0]

    assert "launcher_pid = $PID" in launcher_source
    assert "api_pid = $process.Id" in launcher_source
    assert "Get-Content -LiteralPath $endpointPath -Raw | ConvertFrom-Json" in stop_function
    assert "$endpoint.launcher_pid" in stop_function
    assert "$endpoint.api_pid" in stop_function
    assert "Stop-Process -Id $apiPid" in stop_function
    assert stop_function.index("Stop-Process -Id $apiPid") < stop_function.index(
        "$launcherProcess.WaitForExit"
    )


def test_p01_v4_runner_rebuilds_the_path_safe_runtime_before_acceptance() -> None:
    """The Windows handoff must rebuild the installer, not retest the old payload."""
    runner = REPOSITORY_ROOT / "Run-P01-V4-PathSafe-Rebuild.ps1"

    assert runner.is_file()
    source = runner.read_text(encoding="utf-8")
    assert "scripts\\prepare-runtime.ps1" in source
    assert "scripts\\build-release.ps1" in source
    assert "tests\\release\\windows-acceptance.ps1" in source
    assert "F:\\Video" in source
    assert "Remove-Item" not in source


def test_p01_v4_runner_uses_a_fresh_staging_directory_on_every_rebuild() -> None:
    """A locked payload from an earlier run must not block the next rebuild."""
    runner = REPOSITORY_ROOT / "Run-P01-V4-PathSafe-Rebuild.ps1"
    source = runner.read_text(encoding="ascii")

    assert "Get-Date" in source
    assert "release-v4-" in source
    assert "-Output $buildOutput" in source


def test_p01_v4_runner_uses_a_fresh_installer_output_directory() -> None:
    """A locked installer from a prior run must not block the next rebuild."""
    runner = REPOSITORY_ROOT / "Run-P01-V4-PathSafe-Rebuild.ps1"
    source = runner.read_text(encoding="ascii")

    assert "InstallerOutputDirectory" in source
    assert "release-p01-" in source
    assert "-InstallerOutputDirectory $installerOutputDirectory" in source
    assert "$artifactManifest = Join-Path $installerOutputDirectory" in source
    assert "-ArtifactManifest $artifactManifest" in source
