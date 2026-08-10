from collections import namedtuple
from pathlib import Path

from workbench.diagnostics.center import CHECK_IDS, DiagnosticCenter
from workbench.diagnostics.models import DiagnosticCategory, DiagnosticStatus
from workbench.diagnostics.probes import (
    HeyGenHealthSnapshot,
    HeyGenHealthState,
    _configuration_check,
    _database_integrity_check,
    _disk_space_check,
    build_default_probes,
)

DiskUsage = namedtuple("DiskUsage", "total used free")


def test_default_probes_return_all_checks_without_internal_failures(tmp_path: Path) -> None:
    report = DiagnosticCenter(tmp_path).run()

    assert tuple(check.check_id for check in report.checks) == CHECK_IDS
    assert all(check.code != "DIAGNOSTIC_PROBE_FAILED" for check in report.checks)


def test_disk_space_thresholds_are_green_yellow_and_red(tmp_path: Path) -> None:
    gib = 1024**3

    green = _disk_space_check(
        tmp_path, disk_usage=lambda _: DiskUsage(20 * gib, 10 * gib, 10 * gib)
    )
    yellow = _disk_space_check(
        tmp_path, disk_usage=lambda _: DiskUsage(20 * gib, 17 * gib, 3 * gib)
    )
    red = _disk_space_check(
        tmp_path, disk_usage=lambda _: DiskUsage(20 * gib, 19.5 * gib, int(0.5 * gib))
    )

    assert green.status == DiagnosticStatus.GREEN
    assert yellow.status == DiagnosticStatus.YELLOW
    assert red.status == DiagnosticStatus.RED
    assert red.category == DiagnosticCategory.STORAGE
    assert red.code == "DISK_SPACE_CRITICAL"


def test_corrupt_workspace_database_is_classified_as_storage_failure(tmp_path: Path) -> None:
    (tmp_path / "workspace.db").write_bytes(b"not-a-sqlite-database")

    check = _database_integrity_check(tmp_path)

    assert check.status == DiagnosticStatus.RED
    assert check.category == DiagnosticCategory.STORAGE
    assert check.code == "DATABASE_INTEGRITY_FAILED"
    assert check.evidence["database"] == "workspace.db"


def test_configuration_check_prefers_the_explicit_diagnostic_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project_workspace = tmp_path / "isolated-project-workspace"
    diagnostic_target = tmp_path / "real-workspace"
    runtime_root = tmp_path / "runtime"
    project_workspace.mkdir()
    diagnostic_target.mkdir()
    runtime_root.mkdir()
    monkeypatch.setenv("WORKBENCH_WORKSPACE", str(project_workspace))
    monkeypatch.setenv("WORKBENCH_DIAGNOSTIC_ROOT", str(diagnostic_target))
    monkeypatch.setenv("WORKBENCH_RUNTIME_ROOT", str(runtime_root))

    check = _configuration_check(diagnostic_target)

    assert check.status == DiagnosticStatus.GREEN
    assert check.code == "CONFIGURATION_OK"


def test_heygen_authentication_failure_is_not_misclassified_as_network(
    tmp_path: Path,
) -> None:
    probes = build_default_probes(
        tmp_path,
        heygen_probe=lambda: HeyGenHealthSnapshot(
            state=HeyGenHealthState.AUTHENTICATION,
            has_secret_reference=True,
            voice_count=None,
            error_code="heygen_authentication_failed",
        ),
    )

    report = DiagnosticCenter(tmp_path, probes=probes).run()
    connectivity = next(check for check in report.checks if check.check_id == "heygen_connectivity")
    secret = next(check for check in report.checks if check.check_id == "secret_references")

    assert connectivity.status == DiagnosticStatus.RED
    assert connectivity.category == DiagnosticCategory.AUTHENTICATION
    assert connectivity.code == "HEYGEN_AUTHENTICATION_FAILED"
    assert secret.status == DiagnosticStatus.GREEN
    assert "api" not in str(secret.evidence).lower()
