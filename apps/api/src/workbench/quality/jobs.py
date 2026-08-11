from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .engine import QualityService
from .models import (
    PageSpan,
    QualityPolicy,
    QualityReport,
    QualityResult,
    QualityTarget,
    SubtitlePlacement,
    SubtitleSpan,
)


class QualityJobStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"


class QualityJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    video_path: str = Field(min_length=1, max_length=300)
    render_job_id: UUID | None = None
    expected_width: int = Field(default=1920, gt=0)
    expected_height: int = Field(default=1080, gt=0)
    expected_fps: float = Field(default=30, gt=0)
    expected_video_codec: str = Field(default="h264", min_length=1, max_length=32)
    expected_audio_codec: str = Field(default="aac", min_length=1, max_length=32)
    expected_audio_channels: int | None = Field(default=None, gt=0)
    expected_duration_ms: int = Field(ge=0)
    duration_tolerance_ms: int = Field(default=100, ge=0)
    pages: list[PageSpan] = Field(default_factory=list)
    audio_pages: list[PageSpan] = Field(default_factory=list)
    subtitles: list[SubtitleSpan] = Field(default_factory=list)
    placements: list[SubtitlePlacement] = Field(default_factory=list)
    policy: QualityPolicy = Field(default_factory=QualityPolicy)


class QualityJobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    project_id: UUID
    render_job_id: UUID
    status: QualityJobStatus
    report: QualityReport | None = None
    error_code: str | None = None
    error: str | None = None
    confirmed_issue_ids: list[UUID] = Field(default_factory=list)
    retry_of_job_id: UUID | None = None
    retry_count: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class QualityJobService:
    """Small durable-boundary adapter for quality jobs.

    The first implementation executes synchronously, but keeps the job and
    request boundaries explicit so the existing worker can adopt it without
    changing the quality contract.
    """

    def __init__(
        self,
        root: Path,
        analyzer: QualityService | None = None,
        project_dir_resolver: Callable[[UUID], str] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.analyzer = analyzer or QualityService()
        self.project_dir_resolver = project_dir_resolver
        self._jobs: dict[UUID, QualityJobRecord] = {}
        self._requests: dict[UUID, QualityJobRequest] = {}
        self._lock = RLock()
        self._load_records()

    def submit(
        self,
        project_id: UUID,
        request: QualityJobRequest,
        *,
        retry_of_job_id: UUID | None = None,
        retry_count: int = 0,
    ) -> QualityJobRecord:
        job_id = uuid4()
        render_job_id = request.render_job_id or uuid4()
        record = QualityJobRecord(
            job_id=job_id,
            project_id=project_id,
            render_job_id=render_job_id,
            status=QualityJobStatus.RUNNING,
            retry_of_job_id=retry_of_job_id,
            retry_count=retry_count,
        )
        with self._lock:
            self._jobs[job_id] = record
            self._requests[job_id] = request
            self._persist(record)

        try:
            target = self._target(project_id, request)
            report_path = self._report_path(project_id, job_id)
            report = self.analyzer.analyze(
                project_id=project_id,
                render_job_id=render_job_id,
                target=target,
                policy=request.policy,
                report_path=report_path,
                report_relative_path=self._report_relative_path(job_id),
            )
            status = (
                QualityJobStatus.BLOCKED
                if report.result is QualityResult.BLOCKED
                else QualityJobStatus.SUCCEEDED
            )
            record = record.model_copy(
                update={"status": status, "report": report, "updated_at": datetime.now(UTC)}
            )
        except QualityPathError as error:
            record = record.model_copy(
                update={
                    "status": QualityJobStatus.FAILED,
                    "error_code": error.code,
                    "error": str(error),
                    "updated_at": datetime.now(UTC),
                }
            )
        except Exception:  # noqa: BLE001 - job boundary must persist failures
            record = record.model_copy(
                update={
                    "status": QualityJobStatus.FAILED,
                    "error_code": "quality_analysis_failed",
                    "error": _PUBLIC_ANALYSIS_FAILURE,
                    "updated_at": datetime.now(UTC),
                }
            )
        with self._lock:
            self._jobs[job_id] = record
            self._persist(record)
        return record

    def get(self, project_id: UUID, job_id: UUID | str) -> QualityJobRecord:
        normalized_job_id = job_id if isinstance(job_id, UUID) else UUID(str(job_id))
        with self._lock:
            record = self._jobs.get(normalized_job_id)
        if record is None or record.project_id != project_id:
            raise KeyError(normalized_job_id)
        return record

    def latest(self, project_id: UUID) -> QualityJobRecord:
        with self._lock:
            records = [item for item in self._jobs.values() if item.project_id == project_id]
        if not records:
            raise KeyError(project_id)
        return max(records, key=lambda item: item.updated_at)

    def retry(self, project_id: UUID, job_id: UUID) -> QualityJobRecord:
        with self._lock:
            record = self.get(project_id, job_id)
            request = self._requests.get(job_id)
            already_retried = any(
                item.retry_of_job_id == record.job_id for item in self._jobs.values()
            )
        if request is None:
            raise KeyError(job_id)
        if record.retry_count >= 1 or already_retried:
            raise QualityRetryLimitError(job_id)
        return self.submit(
            project_id,
            request,
            retry_of_job_id=record.job_id,
            retry_count=record.retry_count + 1,
        )

    def confirm_issue(self, project_id: UUID, job_id: UUID, issue_id: UUID) -> QualityJobRecord:
        record = self.get(project_id, job_id)
        if record.report is None or not any(
            issue.issue_id == issue_id for issue in record.report.issues
        ):
            raise KeyError(issue_id)
        if issue_id not in record.confirmed_issue_ids:
            record = record.model_copy(
                update={
                    "confirmed_issue_ids": [*record.confirmed_issue_ids, issue_id],
                    "updated_at": datetime.now(UTC),
                }
            )
            with self._lock:
                self._jobs[record.job_id] = record
                self._persist(record)
        return record

    def evidence_path(self, project_id: UUID, relative_path: str) -> Path:
        candidate = self._safe_path(self._project_root(project_id), relative_path)
        if not candidate.is_file():
            raise FileNotFoundError(relative_path)
        return candidate

    def _target(self, project_id: UUID, request: QualityJobRequest) -> QualityTarget:
        project_root = self._project_root(project_id)
        return QualityTarget(
            video_path=self._safe_path(project_root, request.video_path),
            expected_width=request.expected_width,
            expected_height=request.expected_height,
            expected_fps=request.expected_fps,
            expected_video_codec=request.expected_video_codec,
            expected_audio_codec=request.expected_audio_codec,
            expected_audio_channels=request.expected_audio_channels,
            expected_duration_ms=request.expected_duration_ms,
            duration_tolerance_ms=request.duration_tolerance_ms,
            pages=request.pages,
            audio_pages=request.audio_pages,
            subtitles=request.subtitles,
            placements=request.placements,
        )

    def _report_path(self, project_id: UUID, job_id: UUID) -> Path:
        return (
            self._project_root(project_id)
            / "09_日志"
            / "质量检测"
            / f"quality-report-v1-{job_id}.json"
        )

    def _report_relative_path(self, job_id: UUID) -> str:
        return f"09_日志/质量检测/quality-report-v1-{job_id}.json"

    def _project_root(self, project_id: UUID) -> Path:
        project_dir = (
            self.project_dir_resolver(project_id)
            if self.project_dir_resolver is not None
            else str(project_id)
        )
        return self._safe_path(self.root, project_dir, allow_missing=True)

    def _persist(self, record: QualityJobRecord) -> None:
        target = (
            self._project_root(record.project_id)
            / "09_日志"
            / "质量检测"
            / "jobs"
            / f"{record.job_id}.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)
        request = self._requests.get(record.job_id)
        if request is not None:
            request_target = target.with_suffix(".request.json")
            request_temporary = request_target.with_name(f".{request_target.name}.tmp")
            request_temporary.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
            request_temporary.replace(request_target)

    def _load_records(self) -> None:
        for path in self.root.glob("*/09_日志/质量检测/jobs/*.json"):
            try:
                record = QualityJobRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            self._jobs[record.job_id] = record
            request_path = path.with_suffix(".request.json")
            try:
                self._requests[record.job_id] = QualityJobRequest.model_validate_json(
                    request_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError, json.JSONDecodeError):
                continue

    @staticmethod
    def _safe_path(base: Path, relative_path: str, *, allow_missing: bool = False) -> Path:
        candidate = (base / relative_path).resolve()
        try:
            candidate.relative_to(base.resolve())
        except ValueError as error:
            raise QualityPathError(
                "quality_path_outside_project", "path must stay inside project root"
            ) from error
        if not allow_missing and not candidate.exists():
            return candidate
        return candidate


class QualityPathError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class QualityRetryLimitError(ValueError):
    """Raised when a quality job already consumed its one safe retry."""


_PUBLIC_ANALYSIS_FAILURE = "质量分析未完成，请检查运行时日志后重试"


def iter_project_jobs(
    records: Iterable[QualityJobRecord], project_id: UUID
) -> list[QualityJobRecord]:
    return [record for record in records if record.project_id == project_id]
