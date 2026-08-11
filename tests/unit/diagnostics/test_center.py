from collections.abc import Callable
from pathlib import Path

from workbench.diagnostics.center import CHECK_IDS, DiagnosticCenter
from workbench.diagnostics.models import (
    DiagnosticCategory,
    DiagnosticCheck,
    DiagnosticStatus,
)


def _green(check_id: str) -> DiagnosticCheck:
    return DiagnosticCheck(
        check_id=check_id,
        label=check_id,
        status=DiagnosticStatus.GREEN,
        category=DiagnosticCategory.ENVIRONMENT,
        code=f"{check_id.upper()}_OK",
        summary="检查通过",
        impact="无影响",
        remediation="无需处理",
        evidence={"fixture": "green"},
    )


def _fixture_probes(*, crash: str | None = None) -> dict[str, Callable[[], DiagnosticCheck]]:
    probes: dict[str, Callable[[], DiagnosticCheck]] = {}
    for check_id in CHECK_IDS:
        if check_id == crash:
            probes[check_id] = _raise_permission_error
        else:
            probes[check_id] = lambda selected=check_id: _green(selected)
    return probes


def _raise_permission_error() -> DiagnosticCheck:
    raise PermissionError("C:/Users/Private/secret")


def test_center_runs_all_checks_in_stable_order(tmp_path: Path) -> None:
    report = DiagnosticCenter(tmp_path, probes=_fixture_probes()).run()

    assert tuple(check.check_id for check in report.checks) == CHECK_IDS
    assert report.summary == {"green": len(CHECK_IDS), "yellow": 0, "red": 0}


def test_one_broken_probe_does_not_stop_remaining_checks(tmp_path: Path) -> None:
    report = DiagnosticCenter(
        tmp_path,
        probes=_fixture_probes(crash="database_integrity"),
    ).run()

    assert len(report.checks) == len(CHECK_IDS)
    failed = next(check for check in report.checks if check.check_id == "database_integrity")
    assert failed.status == DiagnosticStatus.RED
    assert failed.category == DiagnosticCategory.INTERNAL
    assert failed.code == "DIAGNOSTIC_PROBE_FAILED"
    assert failed.evidence == {"exception_type": "PermissionError"}
    assert "Private" not in failed.summary
    assert report.summary == {"green": len(CHECK_IDS) - 1, "yellow": 0, "red": 1}


def test_mismatched_probe_identifier_becomes_internal_failure(tmp_path: Path) -> None:
    probes = _fixture_probes()
    probes["disk_space"] = lambda: _green("wrong_identifier")

    report = DiagnosticCenter(tmp_path, probes=probes).run()

    failed = next(check for check in report.checks if check.check_id == "disk_space")
    assert failed.code == "DIAGNOSTIC_PROBE_FAILED"
    assert failed.evidence == {"exception_type": "ValueError"}
