from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import insert, or_, select, update
from sqlalchemy.engine import RowMapping

from workbench.domain.enums import JobStatus, JobType
from workbench.domain.models import JobRecord
from workbench.storage.workspace_db import WorkspaceDatabase, jobs

ACTIVE_STATUSES = frozenset(
    {
        JobStatus.QUEUED,
        JobStatus.RUNNING,
        JobStatus.PAUSE_REQUESTED,
        JobStatus.PAUSED,
        JobStatus.CANCEL_REQUESTED,
    }
)

ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.PAUSED, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.PAUSE_REQUESTED,
            JobStatus.CANCEL_REQUESTED,
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
        }
    ),
    JobStatus.PAUSE_REQUESTED: frozenset({JobStatus.PAUSED, JobStatus.CANCEL_REQUESTED}),
    JobStatus.PAUSED: frozenset({JobStatus.QUEUED, JobStatus.CANCELLED}),
    JobStatus.CANCEL_REQUESTED: frozenset({JobStatus.CANCELLED, JobStatus.FAILED}),
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}


@dataclass(frozen=True)
class JobSpec:
    project_id: UUID
    job_type: JobType
    cache_key: str
    input_fingerprint: str | None = None
    idempotency_key: str | None = None
    payload: dict[str, object] | None = None
    page_id: UUID | None = None
    parent_job_id: UUID | None = None
    paid: bool = False
    max_attempts: int | None = None


@dataclass(frozen=True)
class EnqueueResult:
    record: JobRecord
    created: bool


class JobTransitionConflict(RuntimeError):
    pass


class JobRepository:
    def __init__(self, database: WorkspaceDatabase) -> None:
        self.database = database
        self._claim_lock = Lock()

    def enqueue_or_get(self, spec: JobSpec, *, reuse_succeeded: bool = True) -> EnqueueResult:
        with self.database.engine.begin() as connection:
            criteria = [
                jobs.c.project_id == str(spec.project_id),
                jobs.c.job_type == spec.job_type.value,
            ]
            if spec.idempotency_key:
                criteria.append(
                    or_(
                        jobs.c.idempotency_key == spec.idempotency_key,
                        jobs.c.cache_key == spec.cache_key,
                    )
                )
            else:
                criteria.append(jobs.c.cache_key == spec.cache_key)
            existing_row = connection.execute(select(jobs).where(*criteria)).mappings().first()
            if existing_row is not None:
                existing = _to_record(existing_row)
                if existing.status in ACTIVE_STATUSES or (
                    reuse_succeeded and existing.status is JobStatus.SUCCEEDED
                ):
                    return EnqueueResult(existing, False)
                cache_key = f"{spec.cache_key}:retry:{uuid4().hex}"
            else:
                cache_key = spec.cache_key

            now = _utc_now()
            job_id = uuid4()
            configured_attempts = spec.max_attempts or 3
            max_attempts = min(configured_attempts, 2) if spec.paid else configured_attempts
            connection.execute(
                insert(jobs).values(
                    id=str(job_id),
                    project_id=str(spec.project_id),
                    job_type=spec.job_type.value,
                    status=JobStatus.QUEUED.value,
                    cache_key=cache_key,
                    page_id=str(spec.page_id) if spec.page_id else None,
                    progress=0.0,
                    attempts=0,
                    max_attempts=max_attempts,
                    paid=spec.paid,
                    error=None,
                    created_at=now,
                    updated_at=now,
                    input_fingerprint=spec.input_fingerprint,
                    idempotency_key=spec.idempotency_key,
                    parent_job_id=str(spec.parent_job_id) if spec.parent_job_id else None,
                    payload_json=_encode_json(spec.payload or {}),
                    result_json=None,
                    stage="queued",
                    message="已加入渲染队列",
                    error_code=None,
                    revision=1,
                    heartbeat_at=None,
                    started_at=None,
                    finished_at=None,
                )
            )
            row = connection.execute(select(jobs).where(jobs.c.id == str(job_id))).mappings().one()
        return EnqueueResult(_to_record(row), True)

    def enqueue(self, spec: JobSpec) -> UUID:
        return self.enqueue_or_get(spec).record.id

    def get(self, job_id: UUID) -> JobRecord:
        with self.database.connect() as connection:
            row = connection.execute(select(jobs).where(jobs.c.id == str(job_id))).mappings().one()
        return _to_record(row)

    def list_all(self) -> list[JobRecord]:
        with self.database.connect() as connection:
            rows = connection.execute(select(jobs).order_by(jobs.c.created_at)).mappings().all()
        return [_to_record(row) for row in rows]

    def claim_next(self, job_type: JobType) -> JobRecord | None:
        with self._claim_lock, self.database.engine.begin() as connection:
            candidate = connection.execute(
                select(jobs.c.id)
                .where(jobs.c.job_type == job_type.value, jobs.c.status == JobStatus.QUEUED.value)
                .order_by(jobs.c.created_at, jobs.c.id)
                .limit(1)
            ).scalar_one_or_none()
            if candidate is None:
                return None
            now = _utc_now()
            result = connection.execute(
                update(jobs)
                .where(jobs.c.id == candidate, jobs.c.status == JobStatus.QUEUED.value)
                .values(
                    status=JobStatus.RUNNING.value,
                    stage="validating_input",
                    message="正在校验渲染输入",
                    started_at=now,
                    heartbeat_at=now,
                    updated_at=now,
                    revision=jobs.c.revision + 1,
                    error=None,
                    error_code=None,
                )
            )
            if result.rowcount != 1:
                return None
            row = connection.execute(select(jobs).where(jobs.c.id == candidate)).mappings().one()
        return _to_record(row)

    def mark_running(self, job_id: UUID) -> JobRecord:
        return self._transition(job_id, JobStatus.RUNNING, stage="running", message="任务执行中")

    def update_progress(
        self,
        job_id: UUID,
        progress: float,
        *,
        stage: str | None = None,
        message: str | None = None,
        payload: Mapping[str, object] | None = None,
    ) -> JobRecord:
        if not 0.0 <= progress <= 1.0:
            raise ValueError("progress must be between zero and one")
        record = self.get(job_id)
        if progress < record.progress:
            raise ValueError("progress must not decrease")
        values: dict[str, object] = {
            "progress": progress,
            "updated_at": _utc_now(),
            "heartbeat_at": _utc_now(),
            "revision": jobs.c.revision + 1,
        }
        if stage is not None:
            values["stage"] = stage
        if message is not None:
            values["message"] = message[:500]
        if payload is not None:
            values["payload_json"] = _encode_json(payload)
        return self._write(job_id, values)

    def set_progress(self, job_id: UUID, progress: float) -> JobRecord:
        return self.update_progress(job_id, progress)

    def heartbeat(self, job_id: UUID) -> JobRecord:
        now = _utc_now()
        return self._write(
            job_id,
            {"heartbeat_at": now, "updated_at": now, "revision": jobs.c.revision + 1},
        )

    def record_attempt(self, job_id: UUID, error: str | None = None) -> JobRecord:
        record = self.get(job_id)
        values: dict[str, object] = {
            "attempts": record.attempts + 1,
            "updated_at": _utc_now(),
            "revision": jobs.c.revision + 1,
        }
        if error is not None:
            values["error"] = error[:500]
        return self._write(job_id, values)

    def request_pause(self, job_id: UUID) -> JobRecord:
        record = self.get(job_id)
        if record.status in {JobStatus.PAUSED, JobStatus.PAUSE_REQUESTED}:
            return record
        if record.status is JobStatus.QUEUED:
            return self._transition(job_id, JobStatus.PAUSED, stage="paused", message="任务已暂停")
        if record.status is JobStatus.RUNNING:
            return self._transition(
                job_id,
                JobStatus.PAUSE_REQUESTED,
                stage=record.stage,
                message="当前阶段完成后暂停",
            )
        raise JobTransitionConflict(f"cannot pause job in status {record.status.value}")

    def pause(self, job_id: UUID) -> JobRecord:
        return self.request_pause(job_id)

    def mark_paused(self, job_id: UUID) -> JobRecord:
        return self._transition(job_id, JobStatus.PAUSED, stage="paused", message="任务已暂停")

    def resume(self, job_id: UUID) -> JobRecord:
        record = self.get(job_id)
        if record.status is not JobStatus.PAUSED:
            return record
        return self._transition(
            job_id,
            JobStatus.QUEUED,
            stage="queued",
            message="已恢复并重新排队",
        )

    def request_cancel(self, job_id: UUID) -> JobRecord:
        record = self.get(job_id)
        if record.status in {JobStatus.CANCELLED, JobStatus.CANCEL_REQUESTED}:
            return record
        if record.status in {JobStatus.QUEUED, JobStatus.PAUSED}:
            return self._transition(
                job_id,
                JobStatus.CANCELLED,
                stage="cancelled",
                message="任务已取消",
                error_code="render_cancelled",
                finished_at=_utc_now(),
            )
        if record.status in {JobStatus.RUNNING, JobStatus.PAUSE_REQUESTED}:
            return self._transition(
                job_id,
                JobStatus.CANCEL_REQUESTED,
                stage=record.stage,
                message="正在等待当前进程结束后取消",
            )
        raise JobTransitionConflict(f"cannot cancel job in status {record.status.value}")

    def cancel(self, job_id: UUID) -> JobRecord:
        return self._transition(
            job_id,
            JobStatus.CANCELLED,
            stage="cancelled",
            message="任务已取消",
            error_code="render_cancelled",
            finished_at=_utc_now(),
        )

    def succeed(self, job_id: UUID, result: Mapping[str, object] | None = None) -> JobRecord:
        return self._transition(
            job_id,
            JobStatus.SUCCEEDED,
            stage="completed",
            message="渲染与制作包已完成",
            progress=1.0,
            result_json=_encode_json(result) if result is not None else None,
            finished_at=_utc_now(),
            error=None,
            error_code=None,
        )

    def complete(self, job_id: UUID) -> JobRecord:
        return self.succeed(job_id)

    def fail(
        self,
        job_id: UUID,
        error: str,
        error_code: str = "video_export_rejected",
    ) -> JobRecord:
        return self._transition(
            job_id,
            JobStatus.FAILED,
            stage="failed",
            message="渲染任务失败",
            error=error[:500],
            error_code=error_code,
            finished_at=_utc_now(),
        )

    def requeue_for_recovery(self, job_id: UUID) -> JobRecord:
        record = self.get(job_id)
        if record.status is JobStatus.SUCCEEDED:
            return record
        if record.status is JobStatus.PAUSED:
            return self.resume(job_id)
        return record

    def recover_interrupted_jobs(
        self,
        cancel_cleanup: Callable[[JobRecord], None] | None = None,
    ) -> list[JobRecord]:
        with self.database.connect() as connection:
            interrupted_ids = list(
                connection.execute(
                    select(jobs.c.id).where(
                        jobs.c.status.in_(
                            [JobStatus.RUNNING.value, JobStatus.PAUSE_REQUESTED.value]
                        )
                    )
                ).scalars()
            )
            cancelled_ids = list(
                connection.execute(
                    select(jobs.c.id).where(jobs.c.status == JobStatus.CANCEL_REQUESTED.value)
                ).scalars()
            )

        cleanup_failed: set[str] = set()
        if cancel_cleanup is not None:
            for job_id in cancelled_ids:
                try:
                    cancel_cleanup(self.get(UUID(job_id)))
                except Exception:
                    cleanup_failed.add(str(job_id))

        with self.database.engine.begin() as connection:
            if interrupted_ids:
                connection.execute(
                    update(jobs)
                    .where(jobs.c.id.in_(interrupted_ids))
                    .values(
                        status=JobStatus.PAUSED.value,
                        stage="paused",
                        message="应用上次运行期间中断，可继续或取消",
                        error_code="render_worker_interrupted",
                        updated_at=_utc_now(),
                        heartbeat_at=None,
                        revision=jobs.c.revision + 1,
                    )
                )
            successful_cancellations = [
                job_id for job_id in cancelled_ids if str(job_id) not in cleanup_failed
            ]
            if successful_cancellations:
                connection.execute(
                    update(jobs)
                    .where(jobs.c.id.in_(successful_cancellations))
                    .values(
                        status=JobStatus.CANCELLED.value,
                        stage="cancelled",
                        message="应用上次运行期间取消请求未完成，已恢复为已取消",
                        error_code="render_cancelled",
                        updated_at=_utc_now(),
                        heartbeat_at=None,
                        finished_at=_utc_now(),
                        revision=jobs.c.revision + 1,
                    )
                )
            if cleanup_failed:
                connection.execute(
                    update(jobs)
                    .where(jobs.c.id.in_(sorted(cleanup_failed)))
                    .values(
                        status=JobStatus.FAILED.value,
                        stage="failed",
                        message="取消任务的临时文件清理失败",
                        error="temporary render cleanup failed",
                        error_code="render_cancel_cleanup_failed",
                        updated_at=_utc_now(),
                        heartbeat_at=None,
                        finished_at=_utc_now(),
                        revision=jobs.c.revision + 1,
                    )
                )
        return [self.get(UUID(job_id)) for job_id in [*interrupted_ids, *cancelled_ids]]

    def _transition(self, job_id: UUID, target: JobStatus, **values: object) -> JobRecord:
        record = self.get(job_id)
        if record.status is target:
            return record
        if target not in ALLOWED_TRANSITIONS[record.status]:
            raise JobTransitionConflict(
                f"cannot transition job from {record.status.value} to {target.value}"
            )
        values["status"] = target.value
        values.setdefault("updated_at", _utc_now())
        values.setdefault("revision", jobs.c.revision + 1)
        return self._write(job_id, values, expected_status=record.status)

    def _write(
        self,
        job_id: UUID,
        values: dict[str, object],
        *,
        expected_status: JobStatus | None = None,
    ) -> JobRecord:
        if "result_json" not in values and "result" in values:
            values["result_json"] = _encode_json(values.pop("result"))
        with self.database.engine.begin() as connection:
            statement = update(jobs).where(jobs.c.id == str(job_id))
            if expected_status is not None:
                statement = statement.where(jobs.c.status == expected_status.value)
            result = connection.execute(statement.values(**values))
            if result.rowcount != 1:
                raise JobTransitionConflict(f"job transition lost race for {job_id}")
        return self.get(job_id)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _encode_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _decode_json(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return default


def _to_record(row: RowMapping) -> JobRecord:
    payload: dict[str, Any] = dict(row)
    payload["payload"] = _decode_json(payload.pop("payload_json", None), {})
    payload["result"] = _decode_json(payload.pop("result_json", None), None)
    return JobRecord.model_validate(payload)
