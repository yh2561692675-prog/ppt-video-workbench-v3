from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts/windows_effect_acceptance_lib.ps1"
ENTRY = ROOT / "scripts/windows_effect_acceptance.ps1"
PESTER = ROOT / "tests/release/windows-effect-isolation.Tests.ps1"


def test_isolation_helper_exposes_required_functions_and_ascii_source() -> None:
    source = HELPER.read_bytes()
    text = source.decode("ascii")
    for function_name in (
        "Assert-AcceptanceIsolation",
        "Get-FreeAcceptancePort",
        "Start-OwnedProcess",
        "Stop-OwnedProcess",
        "Write-EvidenceRecord",
    ):
        assert f"function {function_name}" in text
    assert all(byte < 128 for byte in source)


def test_entrypoint_uses_isolated_roots_and_helper() -> None:
    source = ENTRY.read_text(encoding="ascii")
    assert "$helperPath" in source
    assert ". $helperPath" in source
    assert "Assert-AcceptanceIsolation" in source
    assert "InstallRoot" in source
    assert "WorkspaceRoot" in source
    assert "RunTests" in source
    for marker in (
        "CandidateManifest",
        "ArtifactManifest",
        "SampleManifest",
        "FeaturePolicy",
        "DynamicEvidence",
        "DynamicOutputRoot",
        "DynamicReport",
        "effects_dynamic_acceptance.py",
        "RequireEffectsV2",
        "RequireEffectsFallback",
    ):
        assert marker in source
    assert all(byte < 128 for byte in ENTRY.read_bytes())


def test_pester_gate_covers_database_port_process_and_ascii_boundaries() -> None:
    source = PESTER.read_text(encoding="ascii")
    for marker in (
        "E_ISOLATION_DB",
        "E_PORT_UNAVAILABLE",
        "E_PROCESS_NOT_OWNED",
        "Get-FreeAcceptancePort",
        "Start-OwnedProcess",
        "Stop-OwnedProcess",
        "ASCII",
    ):
        assert marker in source
    assert all(byte < 128 for byte in PESTER.read_bytes())
