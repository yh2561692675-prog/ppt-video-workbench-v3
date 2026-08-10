import subprocess
from pathlib import Path

import pytest
import workbench.diagnostics.probes as probes
from workbench.diagnostics.models import DiagnosticCategory, DiagnosticCheck, DiagnosticStatus


class _BrokenSocket:
    def __enter__(self) -> "_BrokenSocket":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def bind(self, _: object) -> None:
        raise OSError("address unavailable")


def _snapshot(
    state: probes.HeyGenHealthState,
    *,
    secret: bool = True,
    voices: int | None = None,
) -> probes.HeyGenHealthSnapshot:
    return probes.HeyGenHealthSnapshot(
        state=state,
        has_secret_reference=secret,
        voice_count=voices,
        error_code=f"fixture_{state.value}",
    )


def test_known_fault_injection_recognition_rate_is_at_least_95_percent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gib = 1024**3
    scenarios: list[tuple[str, DiagnosticCheck, DiagnosticCategory]] = []

    scenarios.extend(
        [
            (
                "disk-low",
                probes._disk_space_check(
                    tmp_path,
                    disk_usage=lambda _: type("Usage", (), {"free": 3 * gib})(),
                ),
                DiagnosticCategory.STORAGE,
            ),
            (
                "disk-critical",
                probes._disk_space_check(
                    tmp_path,
                    disk_usage=lambda _: type("Usage", (), {"free": gib // 2})(),
                ),
                DiagnosticCategory.STORAGE,
            ),
        ]
    )

    corrupt_root = tmp_path / "corrupt"
    corrupt_root.mkdir()
    (corrupt_root / "workspace.db").write_bytes(b"broken")
    scenarios.append(
        (
            "database-corrupt",
            probes._database_integrity_check(corrupt_root),
            DiagnosticCategory.STORAGE,
        )
    )
    scenarios.append(
        (
            "database-missing",
            probes._database_integrity_check(tmp_path / "new"),
            DiagnosticCategory.STORAGE,
        )
    )

    scenarios.extend(
        [
            (
                "heygen-unconfigured",
                probes._heygen_connectivity_check(
                    _snapshot(probes.HeyGenHealthState.UNCONFIGURED, secret=False)
                ),
                DiagnosticCategory.CONFIGURATION,
            ),
            (
                "heygen-auth",
                probes._heygen_connectivity_check(
                    _snapshot(probes.HeyGenHealthState.AUTHENTICATION)
                ),
                DiagnosticCategory.AUTHENTICATION,
            ),
            (
                "heygen-network",
                probes._heygen_connectivity_check(_snapshot(probes.HeyGenHealthState.NETWORK)),
                DiagnosticCategory.NETWORK,
            ),
            (
                "heygen-provider",
                probes._heygen_connectivity_check(_snapshot(probes.HeyGenHealthState.PROVIDER)),
                DiagnosticCategory.PROVIDER,
            ),
            (
                "heygen-voices-empty",
                probes._heygen_voices_check(
                    _snapshot(probes.HeyGenHealthState.AVAILABLE, voices=0)
                ),
                DiagnosticCategory.PROVIDER,
            ),
            (
                "secret-reference-missing",
                probes._secret_reference_check(
                    _snapshot(probes.HeyGenHealthState.UNCONFIGURED, secret=False)
                ),
                DiagnosticCategory.CONFIGURATION,
            ),
        ]
    )

    with monkeypatch.context() as patch:
        patch.setenv("WORKBENCH_RUNTIME_ROOT", str(tmp_path / "missing-runtime"))
        scenarios.append(
            (
                "installation-manifest-missing",
                probes._installation_manifest_check(tmp_path),
                DiagnosticCategory.ENVIRONMENT,
            )
        )

    with monkeypatch.context() as patch:
        patch.setenv("WORKBENCH_WORKSPACE", str(tmp_path / "other-workspace"))
        patch.delenv("WORKBENCH_RUNTIME_ROOT", raising=False)
        scenarios.append(
            (
                "workspace-config-mismatch",
                probes._configuration_check(tmp_path),
                DiagnosticCategory.CONFIGURATION,
            )
        )

    with monkeypatch.context() as patch:
        patch.setenv("WORKBENCH_WORKSPACE", str(tmp_path))
        patch.setenv("WORKBENCH_RUNTIME_ROOT", str(tmp_path / "missing-runtime"))
        scenarios.append(
            (
                "runtime-config-missing",
                probes._configuration_check(tmp_path),
                DiagnosticCategory.CONFIGURATION,
            )
        )

    with monkeypatch.context() as patch:
        patch.setattr(probes, "_ffmpeg_executable", lambda: None)
        scenarios.append(
            (
                "ffmpeg-missing",
                probes._ffmpeg_runtime_check(),
                DiagnosticCategory.ENVIRONMENT,
            )
        )
        scenarios.append(
            (
                "encoder-unavailable",
                probes._video_encoder_check(),
                DiagnosticCategory.PROCESSING,
            )
        )

    with monkeypatch.context() as patch:
        patch.setattr(probes, "_ffmpeg_executable", lambda: tmp_path / "ffmpeg.exe")
        patch.setattr(
            probes,
            "_run_command",
            lambda _: subprocess.CompletedProcess([], 1, "", "failed"),
        )
        scenarios.append(
            (
                "ffmpeg-unusable",
                probes._ffmpeg_runtime_check(),
                DiagnosticCategory.PROCESSING,
            )
        )

    original_write_bytes = Path.write_bytes
    with monkeypatch.context() as patch:

        def deny_diagnostic_write(path: Path, payload: bytes) -> int:
            if path.name.startswith(".diagnostic-"):
                raise PermissionError("denied")
            return original_write_bytes(path, payload)

        patch.setattr(Path, "write_bytes", deny_diagnostic_write)
        scenarios.append(
            (
                "workspace-not-writable",
                probes._workspace_permissions_check(tmp_path / "denied"),
                DiagnosticCategory.STORAGE,
            )
        )

    with monkeypatch.context() as patch:
        patch.setattr(probes.socket, "socket", lambda *_: _BrokenSocket())
        scenarios.append(
            (
                "loopback-bind-failed",
                probes._loopback_port_check(),
                DiagnosticCategory.NETWORK,
            )
        )

    with monkeypatch.context() as patch:
        patch.setattr(
            probes.tempfile,
            "NamedTemporaryFile",
            lambda **_: (_ for _ in ()).throw(PermissionError("temp denied")),
        )
        scenarios.append(
            (
                "temp-not-writable",
                probes._temporary_directory_check(),
                DiagnosticCategory.STORAGE,
            )
        )

    scenarios.append(
        (
            "python-runtime-incomplete",
            probes._python_runtime_check(
                platform_name="nt",
                frozen=True,
                executable=tmp_path / "api" / "workbench.exe",
            ),
            DiagnosticCategory.ENVIRONMENT,
        )
    )

    assert len(scenarios) == 20
    recognized = sum(
        check.status != DiagnosticStatus.GREEN and check.category == expected_category
        for _, check, expected_category in scenarios
    )
    assert recognized / len(scenarios) >= 0.95
