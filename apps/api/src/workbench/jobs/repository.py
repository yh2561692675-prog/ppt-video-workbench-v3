from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import desc, insert, or_, select, update
from sqlalchemy.engine import RowMapping

from workbench.domain.enums import JobStatus, JobType
from workbench.domain.models import JobRecord
from workbench.storage.workspace_db import (
    WorkspaceDatabase,
    artifact_publications,
    job_attempts,
    job_checkpoints,
    jobs,
)

from .contracts import (
    ArtifactPublicationRecord,
    JobAttemptRecord,
    JobCheckpointRecord,
    ResourceRequest,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

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
    JobStatus.QUEUED: frozenset(
        {JobStatus.RUNNING, JobStatus.PAUSED, JobStatus.NEEDS_CONFIRMATION, JobStatus.CANCELLED}
    ),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.PAUSE_REQUESTED,
            JobStatus.NEEDS_CONFIRMATION,
            JobStatus.CANCEL_REQUESTED,
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
        }
    ),
    # A pause request is cooperative: the in-flight stage may still reach a
    # terminal result before it observes the request.  Do not let shutdown
    # overwrite that completed work with a stale pause state.
    JobStatus.PAUSE_REQUESTED: frozenset(
        {
            JobStatus.PAUSED,
            JobStatus.NEEDS_CONFIRMATION,
            JobStatus.CANCEL_REQUESTED,
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
        }
    ),
    JobStatus.PAUSED: frozenset(
        {JobStatus.QUEUED, JobStatus.NEEDS_CONFIRMATION, JobStatus.CANCELLED}
    ),
    JobStatus.NEEDS_CONFIRMATION: frozenset({JobStatus.QUEUED, JobStatus.CANCELLED}),
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
    priority: int = 0
    resource_request: ResourceRequest = field(default_factory=ResourceRequest)
    runtime_fingerprint: str | None = None


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
                    priority=spec.priority,
                    current_attempt_id=None,
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

    def list_for_project(self, project_id: UUID) -> list[JobRecord]:
        with self.database.connect() as connection:
            rows = (
                connection.execute(
                    select(jobs)
                    .where(jobs.c.project_id == str(project_id))
                    .order_by(desc(jobs.c.created_at))
                )
                .mappings()
                .all()
            )
        return [_to_record(row) for row in rows]

    def claim_next(
        self,
        job_type: JobType,
        *,
        worker_id: str | None = None,
        runtime_fingerprint: str | None = None,
    ) -> JobRecord | None:
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
            previous_generation = connection.execute(
                select(job_attempts.c.generation)
                .where(job_attempts.c.job_id == str(candidate))
                .order_by(desc(job_attempts.c.generation))
                .limit(1)
            ).scalar_one_or_none()
            generation = int(previous_generation or 0) + 1
            attempt_id = uuid4()
            connection.execute(
                insert(job_attempts).values(
                    id=str(attempt_id),
                    job_id=str(candidate),
                    generation=generation,
                    status="running",
                    worker_id=worker_id,
                    runtime_fingerprint=runtime_fingerprint,
                    started_at=now,
                    heartbeat_at=now,
                    finished_at=None,
                    exit_code=None,
                    error_code=None,
                    checkpoint_sequence=None,
                    revision=1,
                )
            )
            result = connection.execute(
                update(jobs)
                .where(jobs.c.id == candidate, jobs.c.status == JobStatus.QUEUED.value)
                .values(
                    status=JobStatus.RUNNING.value,
                    stage="validating_input",
                    message="正在校验渲染输入",
                    started_at=now,
                    heartbeat_at=now,
                    current_attempt_id=str(attempt_id),
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
        return self._write(job_id, values, expected_revision=record.revision)

    def set_progress(self, job_id: UUID, progress: float) -> JobRecord:
        return self.update_progress(job_id, progress)

    def heartbeat(
        self,
        job_id: UUID,
        *,
        attempt_id: UUID | None = None,
        generation: int | None = None,
    ) -> JobRecord:
        now = _utc_now()
        record = self.get(job_id)
        if attempt_id is not None and record.current_attempt_id != attempt_id:
            raise JobTransitionConflict("job heartbeat belongs to a stale attempt")
        if generation is not None:
            current = self.current_attempt(job_id)
            if current is None or current.generation != generation:
                raise JobTransitionConflict("job heartbeat belongs to a stale generation")
        updated = self._write(
            job_id,
            {"heartbeat_at": now, "updated_at": now, "revision": jobs.c.revision + 1},
            expected_revision=record.revision,
        )
        if record.current_attempt_id is not None:
            with self.database.engine.begin() as connection:
                connection.execute(
                    update(job_attempts)
                    .where(
                        job_attempts.c.id == str(record.current_attempt_id),
                        job_attempts.c.status == "running",
                    )
                    .values(
                        heartbeat_at=now,
                        revision=job_attempts.c.revision + 1,
                    )
                )
        return updated

    def current_attempt(self, job_id: UUID) -> JobAttemptRecord | None:
        record = self.get(job_id)
        if record.current_attempt_id is None:
            return None
        with self.database.connect() as connection:
            row = (
                connection.execute(
                    select(job_attempts).where(job_attempts.c.id == str(record.current_attempt_id))
                )
                .mappings()
                .first()
            )
        return _to_attempt(row) if row is not None else None

    def list_attempts(self, job_id: UUID) -> list[JobAttemptRecord]:
        with self.database.connect() as connection:
            rows = (
                connection.execute(
                    select(job_attempts)
                    .where(job_attempts.c.job_id == str(job_id))
                    .order_by(job_attempts.c.generation)
                )
                .mappings()
                .all()
            )
        return [_to_attempt(row) for row in rows]

    def record_checkpoint(
        self,
        job_id: UUID,
        checkpoint: Mapping[str, object],
        *,
        attempt_id: UUID | None = None,
        sequence: int | None = None,
        checkpoint_hash: str | None = None,
    ) -> JobCheckpointRecord:
        current = self.current_attempt(job_id)
        selected_attempt = attempt_id or (current.id if current is not None else None)
        if selected_attempt is None:
            raise JobTransitionConflict("cannot record checkpoint without an active attempt")
        existing = self.latest_checkpoint(job_id)
        selected_sequence = (
            sequence if sequence is not None else (existing.sequence + 1 if existing else 1)
        )
        if existing is not None and selected_sequence <= existing.sequence:
            raise JobTransitionConflict("checkpoint sequence must increase")
        payload = _encode_json(dict(checkpoint))
        digest = checkpoint_hash or hashlib.sha256(payload.encode("utf-8")).hexdigest()
        now = _utc_now()
        with self.database.engine.begin() as connection:
            connection.execute(
                insert(job_checkpoints).values(
                    job_id=str(job_id),
                    attempt_id=str(selected_attempt),
                    sequence=selected_sequence,
                    checkpoint_json=payload,
                    checkpoint_hash=digest,
                    created_at=now,
                )
            )
            connection.execute(
                update(job_attempts)
                .where(job_attempts.c.id == str(selected_attempt))
                .values(
                    checkpoint_sequence=selected_sequence,
                    heartbeat_at=now,
                    revision=job_attempts.c.revision + 1,
                )
            )
        return JobCheckpointRecord(
            job_id=job_id,
            attempt_id=selected_attempt,
            sequence=selected_sequence,
            checkpoint=dict(checkpoint),
            checkpoint_hash=digest,
            created_at=datetime.fromisoformat(now),
        )

    def latest_checkpoint(self, job_id: UUID) -> JobCheckpointRecord | None:
        history = self.list_checkpoints(job_id)
        return history[0] if history else None

    def list_checkpoints(self, job_id: UUID) -> list[JobCheckpointRecord]:
        with self.database.connect() as connection:
            rows = (
                connection.execute(
                    select(job_checkpoints)
                    .where(job_checkpoints.c.job_id == str(job_id))
                    .order_by(desc(job_checkpoints.c.sequence))
                )
                .mappings()
                .all()
            )
        return [_to_checkpoint(row) for row in rows]

    def reserve_publication(
        self,
        publication_key: str,
        job_id: UUID,
        attempt_id: UUID,
        manifest: Mapping[str, object],
    ) -> ArtifactPublicationRecord:
        payload = _encode_json(dict(manifest))
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        with self.database.engine.begin() as connection:
            self._require_current_attempt(connection, job_id, attempt_id)
            existing = (
                connection.execute(
                    select(artifact_publications).where(
                        artifact_publications.c.publication_key == publication_key
                    )
                )
                .mappings()
                .first()
            )
            if existing is not None:
                return _to_publication(existing)
            connection.execute(
                insert(artifact_publications).values(
                    publication_key=publication_key,
                    job_id=str(job_id),
                    attempt_id=str(attempt_id),
                    state="reserved",
                    manifest_json=payload,
                    manifest_hash=digest,
                    published_at=None,
                    revision=1,
                )
            )
            row = (
                connection.execute(
                    select(artifact_publications).where(
                        artifact_publications.c.publication_key == publication_key
                    )
                )
                .mappings()
                .one()
            )
        return _to_publication(row)

    def publish_publication(
        self,
        publication_key: str,
        *,
        job_id: UUID,
        attempt_id: UUID,
        manifest_hash: str,
    ) -> ArtifactPublicationRecord:
        now = _utc_now()
        with self.database.engine.begin() as connection:
            self._require_current_attempt(connection, job_id, attempt_id)
            result = connection.execute(
                update(artifact_publications)
                .where(
                    artifact_publications.c.publication_key == publication_key,
                    artifact_publications.c.job_id == str(job_id),
                    artifact_publications.c.attempt_id == str(attempt_id),
                    artifact_publications.c.manifest_hash == manifest_hash,
                    artifact_publications.c.state == "reserved",
                )
                .values(
                    state="published",
                    published_at=now,
                    revision=artifact_publications.c.revision + 1,
                )
            )
            if result.rowcount != 1:
                row = (
                    connection.execute(
                        select(artifact_publications).where(
                            artifact_publications.c.publication_key == publication_key
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if row is None:
                    raise JobTransitionConflict("publication reservation not found")
            row = (
                connection.execute(
                    select(artifact_publications).where(
                        artifact_publications.c.publication_key == publication_key
                    )
                )
                .mappings()
                .one()
            )
        return _to_publication(row)

    def reconcile_publication(
        self,
        publication_key: str,
        verifier: Callable[[ArtifactPublicationRecord], bool],
    ) -> ArtifactPublicationRecord:
        with self.database.engine.begin() as connection:
            row = (
                connection.execute(
                    select(artifact_publications).where(
                        artifact_publications.c.publication_key == publication_key
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise JobTransitionConflict("publication reservation not found")
            publication = _to_publication(row)
            if publication.state != "published" or verifier(publication):
                return publication
            connection.execute(
                update(artifact_publications)
                .where(
                    artifact_publications.c.publication_key == publication_key,
                    artifact_publications.c.state == "published",
                )
                .values(state="corrupted", revision=artifact_publications.c.revision + 1)
            )
            reconciled = (
                connection.execute(
                    select(artifact_publications).where(
                        artifact_publications.c.publication_key == publication_key
                    )
                )
                .mappings()
                .one()
            )
        return _to_publication(reconciled)

    def record_attempt(self, job_id: UUID, error: str | None = None) -> JobRecord:
        record = self.get(job_id)
        values: dict[str, object] = {
            "attempts": record.attempts + 1,
            "updated_at": _utc_now(),
            "revision": jobs.c.revision + 1,
        }
        if error is not None:
            values["error"] = error[:500]
        return self._write(job_id, values, expected_revision=record.revision)

    def request_pause(self, job_id: UUID, *, expected_revision: int | None = None) -> JobRecord:
        record = self.get(job_id)
        self._require_expected_revision(record, expected_revision)
        if record.status in {JobStatus.PAUSED, JobStatus.PAUSE_REQUESTED}:
            return record
        if record.status is JobStatus.QUEUED:
            return self._transition(
                job_id,
                JobStatus.PAUSED,
                expected_revision=record.revision,
                stage="paused",
                message="任务已暂停",
            )
        if record.status is JobStatus.RUNNING:
            return self._transition(
                job_id,
                JobStatus.PAUSE_REQUESTED,
                expected_revision=record.revision,
                stage=record.stage,
                message="当前阶段完成后暂停",
            )
        raise JobTransitionConflict(f"cannot pause job in status {record.status.value}")

    def pause(self, job_id: UUID) -> JobRecord:
        return self.request_pause(job_id)

    def mark_paused(self, job_id: UUID) -> JobRecord:
        return self._transition(job_id, JobStatus.PAUSED, stage="paused", message="任务已暂停")

    def resume(self, job_id: UUID, *, expected_revision: int | None = None) -> JobRecord:
        record = self.get(job_id)
        self._require_expected_revision(record, expected_revision)
        if record.status is not JobStatus.PAUSED:
            return record
        return self._transition(
            job_id,
            JobStatus.QUEUED,
            expected_revision=record.revision,
            stage="queued",
            message="已恢复并重新排队",
        )

    def require_manual_confirmation(
        self, job_id: UUID, *, expected_revision: int | None = None
    ) -> JobRecord:
        record = self.get(job_id)
        self._require_expected_revision(record, expected_revision)
        if not record.paid:
            raise JobTransitionConflict("manual confirmation is reserved for paid jobs")
        if record.status is JobStatus.NEEDS_CONFIRMATION:
            return record
        return self._transition(
            job_id,
            JobStatus.NEEDS_CONFIRMATION,
            expected_revision=record.revision,
            stage="manual_confirmation",
            message="paid remote task outcome is unknown; manual confirmation is required",
            error="paid remote task outcome is unknown",
            error_code="paid_remote_result_unknown",
        )

    def confirm_paid_retry(
        self, job_id: UUID, *, expected_revision: int | None = None
    ) -> JobRecord:
        record = self.get(job_id)
        self._require_expected_revision(record, expected_revision)
        if not record.paid or record.status is not JobStatus.NEEDS_CONFIRMATION:
            raise JobTransitionConflict("job is not awaiting paid-result confirmation")
        return self._transition(
            job_id,
            JobStatus.QUEUED,
            expected_revision=record.revision,
            stage="queued",
            message="paid remote result confirmed for retry",
            error=None,
            error_code=None,
        )

    def request_cancel(self, job_id: UUID, *, expected_revision: int | None = None) -> JobRecord:
        record = self.get(job_id)
        self._require_expected_revision(record, expected_revision)
        if record.status in {JobStatus.CANCELLED, JobStatus.CANCEL_REQUESTED}:
            return record
        if record.status in {JobStatus.QUEUED, JobStatus.PAUSED}:
            return self._transition(
                job_id,
                JobStatus.CANCELLED,
                expected_revision=record.revision,
                stage="cancelled",
                message="任务已取消",
                error_code="render_cancelled",
                finished_at=_utc_now(),
            )
        if record.status in {JobStatus.RUNNING, JobStatus.PAUSE_REQUESTED}:
            return self._transition(
                job_id,
                JobStatus.CANCEL_REQUESTED,
                expected_revision=record.revision,
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
                connection.execute(
                    update(job_attempts)
                    .where(
                        job_attempts.c.job_id.in_(interrupted_ids),
                        job_attempts.c.status == "running",
                    )
                    .values(
                        status="expired",
                        heartbeat_at=None,
                        finished_at=_utc_now(),
                        revision=job_attempts.c.revision + 1,
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
                connection.execute(
                    update(job_attempts)
                    .where(
                        job_attempts.c.job_id.in_(successful_cancellations),
                        job_attempts.c.status.in_(["running", "paused"]),
                    )
                    .values(
                        status="cancelled",
                        heartbeat_at=None,
                        finished_at=_utc_now(),
                        revision=job_attempts.c.revision + 1,
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

    def _transition(
        self,
        job_id: UUID,
        target: JobStatus,
        *,
        expected_revision: int | None = None,
        **values: object,
    ) -> JobRecord:
        record = self.get(job_id)
        self._require_expected_revision(record, expected_revision)
        if record.status is target:
            return record
        if target not in ALLOWED_TRANSITIONS[record.status]:
            raise JobTransitionConflict(
                f"cannot transition job from {record.status.value} to {target.value}"
            )
        values["status"] = target.value
        values.setdefault("updated_at", _utc_now())
        values.setdefault("revision", jobs.c.revision + 1)
        updated = self._write(
            job_id,
            values,
            expected_status=record.status,
            expected_revision=record.revision,
        )
        attempt_status = {
            JobStatus.PAUSED: "paused",
            JobStatus.NEEDS_CONFIRMATION: "paused",
            JobStatus.SUCCEEDED: "succeeded",
            JobStatus.FAILED: "failed",
            JobStatus.CANCELLED: "cancelled",
        }.get(target)
        if attempt_status is not None and record.current_attempt_id is not None:
            with self.database.engine.begin() as connection:
                connection.execute(
                    update(job_attempts)
                    .where(job_attempts.c.id == str(record.current_attempt_id))
                    .values(
                        status=attempt_status,
                        finished_at=_utc_now(),
                        heartbeat_at=None,
                        revision=job_attempts.c.revision + 1,
                    )
                )
        return updated

    def _write(
        self,
        job_id: UUID,
        values: dict[str, object],
        *,
        expected_status: JobStatus | None = None,
        expected_revision: int | None = None,
    ) -> JobRecord:
        if "result_json" not in values and "result" in values:
            values["result_json"] = _encode_json(values.pop("result"))
        with self.database.engine.begin() as connection:
            statement = update(jobs).where(jobs.c.id == str(job_id))
            if expected_status is not None:
                statement = statement.where(jobs.c.status == expected_status.value)
            if expected_revision is not None:
                statement = statement.where(jobs.c.revision == expected_revision)
            result = connection.execute(statement.values(**values))
            if result.rowcount != 1:
                raise JobTransitionConflict(f"job transition lost race for {job_id}")
        return self.get(job_id)

    @staticmethod
    def _require_expected_revision(record: JobRecord, expected_revision: int | None) -> None:
        if expected_revision is not None and record.revision != expected_revision:
            raise JobTransitionConflict(
                f"job revision mismatch for {record.id}: expected {expected_revision}, "
                f"current {record.revision}"
            )

    @staticmethod
    def _require_current_attempt(connection: Connection, job_id: UUID, attempt_id: UUID) -> None:
        current_attempt_id = connection.execute(
            select(jobs.c.current_attempt_id).where(jobs.c.id == str(job_id))
        ).scalar_one_or_none()
        if current_attempt_id != str(attempt_id):
            raise JobTransitionConflict("artifact publication belongs to a stale attempt")


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


def _to_attempt(row: RowMapping) -> JobAttemptRecord:
    return JobAttemptRecord.model_validate(dict(row))


def _to_checkpoint(row: RowMapping) -> JobCheckpointRecord:
    payload = dict(row)
    payload["checkpoint"] = _decode_json(payload.pop("checkpoint_json"), {})
    return JobCheckpointRecord.model_validate(payload)


def _to_publication(row: RowMapping) -> ArtifactPublicationRecord:
    payload = dict(row)
    payload["manifest"] = _decode_json(payload.pop("manifest_json"), {})
    return ArtifactPublicationRecord.model_validate(payload)
