from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IssueContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IssueLevel(StrEnum):
    BLOCKING = "blocking"
    CONFIRMATION = "confirmation"
    REQUIRED_WARNING = "required_warning"
    INFO = "info"


class IssueLocation(IssueContractModel):
    page_id: UUID | None = None
    job_id: UUID | None = None
    node: str | None = None
    relative_path: str | None = None


class IssueTimeRange(IssueContractModel):
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> IssueTimeRange:
        if self.end_ms <= self.start_ms:
            raise ValueError("issue time range end must be after start")
        return self


class IssueConfirmation(IssueContractModel):
    id: UUID = Field(default_factory=uuid4)
    issue_id: UUID
    report_id: UUID
    actor: str = Field(min_length=1, max_length=120)
    note: str = Field(min_length=1, max_length=2_000)
    confirmed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PreflightIssue(IssueContractModel):
    issue_id: UUID = Field(default_factory=uuid4)
    check: str = "generic"
    code: str
    level: IssueLevel
    message: str
    action: str
    reason: str | None = None
    time_range: IssueTimeRange | None = None
    location: IssueLocation = Field(default_factory=IssueLocation)
    fingerprint: str = Field(min_length=64, max_length=64)
    blocking: bool = True
    confirmed: bool = False
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_blocking(self) -> PreflightIssue:
        if self.level is IssueLevel.BLOCKING and not self.blocking:
            raise ValueError("blocking issues must have blocking=true")
        return self


class PreflightReport(IssueContractModel):
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    scope: list[str] = Field(default_factory=list)
    input_fingerprint: str = Field(min_length=64, max_length=64)
    check_fingerprints: dict[str, str] = Field(default_factory=dict)
    issues: list[PreflightIssue] = Field(default_factory=list)
    allowed: bool = False
    snapshot_path: str | None = None
    reused_checks: list[str] = Field(default_factory=list)
    executed_checks: list[str] = Field(default_factory=list)


PreflightScope = Literal[
    "materials",
    "content",
    "audio",
    "video",
    "presenter",
    "runtime",
    "resources",
]


class IssueCheckResult(IssueContractModel):
    fingerprint: str = Field(min_length=64, max_length=64)
    issues: list[PreflightIssue] = Field(default_factory=list)


class CleanupPlanRecord(IssueContractModel):
    id: UUID
    project_id: UUID
    status: Literal["estimated", "executed", "failed", "expired"] = "estimated"
    relative_paths: list[str] = Field(default_factory=list)
    bytes_reclaimable: int = Field(default=0, ge=0)
    affected_nodes: list[str] = Field(default_factory=list)
    confirmation_token_digest: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
