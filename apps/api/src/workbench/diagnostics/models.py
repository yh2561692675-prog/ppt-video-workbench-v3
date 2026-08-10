from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class DiagnosticStatus(StrEnum):
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"


class DiagnosticCategory(StrEnum):
    ENVIRONMENT = "ENVIRONMENT"
    CONFIGURATION = "CONFIGURATION"
    AUTHENTICATION = "AUTHENTICATION"
    NETWORK = "NETWORK"
    PROVIDER = "PROVIDER"
    INPUT = "INPUT"
    PROCESSING = "PROCESSING"
    STORAGE = "STORAGE"
    QA = "QA"
    INTERNAL = "INTERNAL"


class DiagnosticCheck(StrictModel):
    check_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    label: str = Field(min_length=1, max_length=80)
    status: DiagnosticStatus
    category: DiagnosticCategory
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,95}$")
    summary: str = Field(min_length=1, max_length=300)
    impact: str = Field(min_length=1, max_length=300)
    remediation: str = Field(min_length=1, max_length=500)
    evidence: dict[str, JsonValue] = Field(default_factory=dict)


class DiagnosticReport(StrictModel):
    report_id: UUID = Field(default_factory=uuid4)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    overall_status: DiagnosticStatus
    summary: dict[str, int]
    checks: tuple[DiagnosticCheck, ...]

    @classmethod
    def build(cls, checks: Iterable[DiagnosticCheck]) -> DiagnosticReport:
        collected = tuple(checks)
        identifiers = [check.check_id for check in collected]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate diagnostic check_id")
        counts = {
            status.value: sum(check.status == status for check in collected)
            for status in DiagnosticStatus
        }
        severity = {
            DiagnosticStatus.GREEN: 0,
            DiagnosticStatus.YELLOW: 1,
            DiagnosticStatus.RED: 2,
        }
        overall = (
            max((check.status for check in collected), key=severity.__getitem__)
            if collected
            else DiagnosticStatus.YELLOW
        )
        return cls(
            overall_status=overall,
            summary=counts,
            checks=collected,
        )


class DiagnosticPackage(StrictModel):
    report_id: UUID
    relative_path: str = Field(min_length=1, max_length=1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
