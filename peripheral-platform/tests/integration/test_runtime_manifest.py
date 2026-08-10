from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = ROOT.parent


def test_runtime_manifest_lists_required_files() -> None:
    runtime_manifest = json.loads(
        (ROOT / "packaging" / "runtime-manifest.json").read_text(encoding="utf-8")
    )
    required = {
        "peripheral/peripheral-host.exe",
        "peripheral/schemas/job-envelope-1.0.json",
        "peripheral/schemas/job-result-1.0.json",
        "peripheral/migrations/0001_s0_core.sql",
    }

    assert required <= set(runtime_manifest["required_files"])
    assert runtime_manifest["python_runtime"] == "3.12"
    assert runtime_manifest["distribution"] == "onedir"


def test_pyinstaller_spec_bundles_protocol_database_and_echo_module() -> None:
    source = (ROOT / "packaging" / "peripheral-host.spec").read_text(encoding="utf-8")

    assert "schemas" in source
    assert "migrations" in source
    assert "peripheral_modules.echo.__main__" in source
    assert 'contents_directory="."' in source
    assert 'name="peripheral"' in source


def test_initialize_script_has_workspace_and_disk_safety_gates() -> None:
    source = (ROOT / "scripts" / "initialize-s0.ps1").read_text(encoding="ascii")

    for directory in (
        "workspace-data",
        "projects",
        "cache",
        "logs",
        "diagnostics",
        "backups",
        "quarantine",
    ):
        assert f'"{directory}"' in source
    assert "5GB" in source
    assert "GetPathRoot" in source
    assert "peripheral.db" in source
    assert "Set-Content" not in source


def test_launcher_degrades_without_killing_unowned_peripheral_processes() -> None:
    source = (REPOSITORY_ROOT / "scripts" / "launcher.ps1").read_text(encoding="ascii")

    assert '$env:PERIPHERAL_ENABLED -eq "true"' in source
    assert "/internal/v1/health" in source
    assert "PERIPHERAL_DEGRADED" in source
    assert "$peripheralProcess.Id" in source
    assert "Get-Process -Name peripheral-host" not in source


def test_release_build_has_enabled_peripheral_gate_and_payload_verification() -> None:
    source = (REPOSITORY_ROOT / "scripts" / "build-release.ps1").read_text(
        encoding="ascii"
    )

    assert "build-s0.ps1" in source
    assert "peripheral\\peripheral-host.exe" in source
    assert "PeripheralEnabled" in source
    assert source.index("build-s0.ps1") < source.index("uv sync --frozen")


def test_verify_script_runs_all_gates_database_checks_and_hash_validation() -> None:
    source = (ROOT / "scripts" / "verify-s0.ps1").read_text(encoding="ascii")

    for suite in ("unit", "contract", "security", "integration"):
        assert f"peripheral-platform/tests/{suite} -v" in source
    assert "python -m compileall -q peripheral-platform/src" in source
    assert "build-s0.ps1" in source
    assert "smoke-s0.ps1" in source
    assert "PRAGMA quick_check" in source
    assert "PRAGMA foreign_key_check" in source
    assert "Get-FileHash" in source
    assert 'Write-Output "S0_ACCEPTANCE=PASS"' in source


def test_smoke_script_captures_packaged_host_startup_diagnostics() -> None:
    source = (ROOT / "scripts" / "smoke-s0.ps1").read_text(encoding="ascii")

    assert "-RedirectStandardOutput" in source
    assert "-RedirectStandardError" in source
    assert "HasExited" in source
    assert "S0 host process exited before becoming healthy" in source


def test_smoke_script_uses_one_available_loopback_port_for_host_and_probes() -> None:
    source = (ROOT / "scripts" / "smoke-s0.ps1").read_text(encoding="ascii")

    assert "function Get-AvailableLoopbackPort" in source
    assert '$port = Get-AvailableLoopbackPort' in source
    assert '$env:PERIPHERAL_PORT = [string]$port' in source
    assert '$baseUrl = "http://127.0.0.1:$port/internal/v1"' in source
    assert '"$baseUrl/health"' in source
    assert '"$baseUrl/jobs"' in source
    assert '"$baseUrl/jobs/$jobId"' in source
    assert '"$baseUrl/jobs/$jobId/artifacts"' in source
    assert "127.0.0.1:8765" not in source


def test_s0_build_runs_only_peripheral_platform_test_suite() -> None:
    source = (ROOT / "scripts" / "build-s0.ps1").read_text(encoding="ascii")

    assert "& $python -m pytest peripheral-platform/tests -q" in source
    assert "& $python -m pytest tests peripheral-platform/tests -q" not in source


def test_readme_contains_operations_degradation_and_non_destructive_rollback() -> None:
    source = (ROOT / "README.md").read_text(encoding="utf-8")

    for topic in (
        "架构边界",
        "环境变量",
        "目录规则",
        "模块契约",
        "Windows 构建",
        "功能开关与降级",
        "数据库备份、恢复与回滚",
    ):
        assert topic in source
    assert "PERIPHERAL_ENABLED=false" in source
    assert "不执行数据库降级 SQL" in source
    assert "保留整个 `F:\\Video`" in source
