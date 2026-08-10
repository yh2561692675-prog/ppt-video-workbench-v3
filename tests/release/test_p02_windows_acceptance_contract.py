from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_p02_runner_builds_installer_and_invokes_isolated_acceptance() -> None:
    runner = ROOT / "Run-P02-Health-Diagnostics.ps1"
    source = runner.read_text(encoding="utf-8")

    source.encode("ascii")
    assert "scripts\\prepare-runtime.ps1" in source
    assert "scripts\\build-release.ps1" in source
    assert "tests\\release\\windows-p02-acceptance.ps1" in source
    assert "-WorkspaceRoot $WorkspaceRoot" in source


def test_p02_windows_acceptance_checks_real_diagnostics_and_safe_bundle() -> None:
    runner = ROOT / "tests" / "release" / "windows-p02-acceptance.ps1"
    source = runner.read_text(encoding="utf-8")

    source.encode("ascii")
    assert '"$baseUrl/api/diagnostics/run"' in source
    assert '"$baseUrl/api/diagnostics/package"' in source
    assert '"$baseUrl/api/health"' in source
    assert "DIAGNOSTIC_PROBE_FAILED" in source
    assert "P02_WINDOWS_ACCEPTANCE=PASS" in source
    assert "P02_WINDOWS_ACCEPTANCE=BLOCK" in source
    assert "Stop-Process -Id $apiPid" in source
    assert "System.IO.Compression.ZipFile" in source
    assert "p02-secret-sentinel" in source


def test_p02_windows_acceptance_does_not_block_or_write_the_active_workspace() -> None:
    runner = ROOT / "tests" / "release" / "windows-p02-acceptance.ps1"
    source = runner.read_text(encoding="utf-8")

    assert "Close the currently running PPT Video Workbench" not in source
    assert '$acceptanceWorkspace = Join-Path $stateRoot "workspace"' in source
    assert "$env:WORKBENCH_WORKSPACE = $acceptanceWorkspace" in source
    assert "$env:WORKBENCH_DIAGNOSTIC_ROOT = $WorkspaceRoot" in source


def test_doctor_prefers_p02_and_keeps_p01_compatibility() -> None:
    source = (ROOT / "scripts" / "doctor.ps1").read_text(encoding="utf-8")

    assert "/api/diagnostics/run" in source
    assert "/api/diagnostics/package" in source
    assert "/api/environment" in source
