from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError
from workbench.diagnostics.models import (
    DiagnosticCategory,
    DiagnosticCheck,
    DiagnosticReport,
    DiagnosticStatus,
)


def _check(
    check_id: str,
    status: DiagnosticStatus,
    *,
    category: DiagnosticCategory = DiagnosticCategory.ENVIRONMENT,
) -> DiagnosticCheck:
    return DiagnosticCheck(
        check_id=check_id,
        label=f"label-{check_id}",
        status=status,
        category=category,
        code=f"{check_id.upper()}_{status.value.upper()}",
        summary=f"summary-{check_id}",
        impact=f"impact-{check_id}",
        remediation=f"remediation-{check_id}",
        evidence={"fixture": check_id},
    )


def test_report_uses_worst_check_as_overall_status() -> None:
    report = DiagnosticReport.build(
        [
            _check("runtime", DiagnosticStatus.GREEN),
            _check("disk", DiagnosticStatus.YELLOW),
            _check("database", DiagnosticStatus.RED),
        ]
    )

    assert report.overall_status == DiagnosticStatus.RED
    assert report.summary == {"green": 1, "yellow": 1, "red": 1}
    assert isinstance(report.report_id, UUID)
    assert report.checked_at.tzinfo is not None


def test_empty_report_is_yellow_instead_of_claiming_health() -> None:
    report = DiagnosticReport.build([])

    assert report.overall_status == DiagnosticStatus.YELLOW
    assert report.summary == {"green": 0, "yellow": 0, "red": 0}


def test_report_rejects_duplicate_check_identifiers() -> None:
    duplicate = _check("disk", DiagnosticStatus.GREEN)

    with pytest.raises(ValueError, match="duplicate diagnostic check_id"):
        DiagnosticReport.build([duplicate, duplicate])


def test_check_rejects_unknown_evidence_types() -> None:
    with pytest.raises(ValidationError):
        DiagnosticCheck(
            check_id="runtime",
            label="运行时",
            status=DiagnosticStatus.GREEN,
            category=DiagnosticCategory.ENVIRONMENT,
            code="RUNTIME_OK",
            summary="可用",
            impact="无",
            remediation="无需处理",
            evidence={"checked_at": datetime.now(UTC)},
        )
