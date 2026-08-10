from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from peripheral_contracts import EventEnvelope, JobEnvelope, JobStatus

from peripheral_host.artifacts import PublishedArtifact
from peripheral_host.database import Database
from peripheral_host.module_runner import JobAttemptRecord


class ConcurrentTransitionError(RuntimeError):
    """The stored job no longer has the caller's expected status."""


@dataclass(frozen=True, slots=True)
class JobRecord:
    job_id: UUID
    project_id: UUID
    envelope: JobEnvelope
    status: JobStatus
    progress: int
    current_attempt: int
    next_attempt_at: datetime | None
    last_error_json: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class StoredEvent:
    sequence: int
    envelope: EventEnvelope


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    artifact_id: UUID
    job_id: UUID
    project_id: UUID
    logical_name: str
    kind: str
    relative_path: str
    version: int
    size_bytes: int
    sha256: str
    verified_at: datetime
    is_current: bool


class JobRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        envelope: JobEnvelope,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> JobRecord:
        if connection is not None:
            return self._create(connection, envelope)
        with self.database.transaction(immediate=True) as owned_connection:
            return self._create(owned_connection, envelope)

    def _create(
        self,
        connection: sqlite3.Connection,
        envelope: JobEnvelope,
    ) -> JobRecord:
        created_at = _utc_text(envelope.created_at)
        connection.execute(
            """
            INSERT OR IGNORE INTO projects(
              project_id, workbench_project_ref, name, created_at, updated_at
            ) VALUES (?, NULL, ?, ?, ?)
            """,
            (str(envelope.project_id), str(envelope.project_id), created_at, created_at),
        )
        try:
            connection.execute(
                """
                INSERT INTO jobs(
                  job_id, project_id, job_type, schema_version, status, priority,
                  idempotency_key, requested_by, request_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(envelope.job_id),
                    str(envelope.project_id),
                    envelope.job_type,
                    envelope.schema_version,
                    JobStatus.QUEUED.value,
                    envelope.priority,
                    envelope.idempotency_key,
                    envelope.requested_by,
                    envelope.model_dump_json(),
                    created_at,
                    created_at,
                ),
            )
        except sqlite3.IntegrityError:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_type=? AND idempotency_key=?",
                (envelope.job_type, envelope.idempotency_key),
            ).fetchone()
            if row is None:
                raise
            return _job_record(row)
        row = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?", (str(envelope.job_id),)
        ).fetchone()
        if row is None:
            raise RuntimeError("created job could not be reloaded")
        return _job_record(row)

    def get_by_idempotency(
        self,
        job_type: str,
        idempotency_key: str,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> JobRecord | None:
        if connection is not None:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_type=? AND idempotency_key=?",
                (job_type, idempotency_key),
            ).fetchone()
            return None if row is None else _job_record(row)
        with self.database.read_connection() as owned_connection:
            row = owned_connection.execute(
                "SELECT * FROM jobs WHERE job_type=? AND idempotency_key=?",
                (job_type, idempotency_key),
            ).fetchone()
        return None if row is None else _job_record(row)

    def get(self, job_id: UUID) -> JobRecord | None:
        with self.database.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE job_id=?", (str(job_id),)
            ).fetchone()
        return None if row is None else _job_record(row)

    def count(self) -> int:
        with self.database.read_connection() as connection:
            row = connection.execute("SELECT COUNT(*) FROM jobs").fetchone()
        return 0 if row is None else int(row[0])

    def claim_next(
        self,
        now: datetime,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> JobRecord | None:
        if connection is not None:
            return self._claim_next(connection, now)
        with self.database.transaction(immediate=True) as owned_connection:
            return self._claim_next(owned_connection, now)

    @staticmethod
    def _claim_next(
        connection: sqlite3.Connection,
        now: datetime,
    ) -> JobRecord | None:
        row = connection.execute(
                """
                SELECT * FROM jobs
                WHERE status=?
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """,
                (JobStatus.QUEUED.value,),
            ).fetchone()
        if row is None:
            return None
        updated_at = _utc_text(now)
        updated = connection.execute(
            """
            UPDATE jobs
            SET status=?, current_attempt=current_attempt+1, updated_at=?
            WHERE job_id=? AND status=?
            """,
            (
                JobStatus.RUNNING.value,
                updated_at,
                row["job_id"],
                JobStatus.QUEUED.value,
            ),
        )
        if updated.rowcount != 1:
            raise ConcurrentTransitionError("job was claimed concurrently")
        claimed = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?", (row["job_id"],)
        ).fetchone()
        if claimed is None:
            raise RuntimeError("claimed job could not be reloaded")
        return _job_record(claimed)

    def list_by_status(self, status: JobStatus) -> list[JobRecord]:
        with self.database.read_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs WHERE status=? ORDER BY created_at",
                (status.value,),
            ).fetchall()
        return [_job_record(row) for row in rows]

    def list_due_retries(self, now: datetime) -> list[JobRecord]:
        with self.database.read_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM jobs
                WHERE status=? AND next_attempt_at IS NOT NULL AND next_attempt_at<=?
                ORDER BY next_attempt_at, priority DESC, created_at
                """,
                (JobStatus.RETRY_WAIT.value, _utc_text(now)),
            ).fetchall()
        return [_job_record(row) for row in rows]

    def transition(
        self,
        job_id: UUID,
        expected: JobStatus,
        target: JobStatus,
        *,
        connection: sqlite3.Connection | None = None,
        **fields: Any,
    ) -> JobRecord:
        if connection is not None:
            return self._transition(connection, job_id, expected, target, fields)
        with self.database.transaction(immediate=True) as owned_connection:
            return self._transition(owned_connection, job_id, expected, target, fields)

    def _transition(
        self,
        connection: sqlite3.Connection,
        job_id: UUID,
        expected: JobStatus,
        target: JobStatus,
        fields: dict[str, Any],
    ) -> JobRecord:
        allowed_fields = {
            "progress",
            "current_attempt",
            "next_attempt_at",
            "last_error_json",
        }
        unknown = set(fields) - allowed_fields
        if unknown:
            raise ValueError(f"unsupported transition fields: {sorted(unknown)}")
        assignments = ["status=?", "updated_at=?"]
        values: list[Any] = [target.value, _utc_text(datetime.now(UTC))]
        for name, value in fields.items():
            assignments.append(f"{name}=?")
            values.append(_database_value(value))
        values.extend((str(job_id), expected.value))
        cursor = connection.execute(
            f"UPDATE jobs SET {', '.join(assignments)} WHERE job_id=? AND status=?",
            values,
        )
        if cursor.rowcount != 1:
            raise ConcurrentTransitionError(
                f"job {job_id} is not in expected state {expected.value}"
            )
        row = connection.execute(
            "SELECT * FROM jobs WHERE job_id=?", (str(job_id),)
        ).fetchone()
        if row is None:
            raise RuntimeError("transitioned job could not be reloaded")
        return _job_record(row)

    def mark_orphaned_running_for_recovery(self, now: datetime) -> int:
        error_json = json.dumps(
            {
                "category": "PROCESSING",
                "code": "HOST_RESTARTED_DURING_ATTEMPT",
                "message": "Peripheral host restarted during an attempt",
                "retryable": True,
                "details": {},
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        with self.database.transaction(immediate=True) as connection:
            cursor = connection.execute(
                """
                UPDATE jobs
                SET status=?, next_attempt_at=?, last_error_json=?, updated_at=?
                WHERE status=?
                """,
                (
                    JobStatus.RETRY_WAIT.value,
                    _utc_text(now),
                    error_json,
                    _utc_text(now),
                    JobStatus.RUNNING.value,
                ),
            )
            return cursor.rowcount


class EventRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def append(
        self,
        event: EventEnvelope,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> int:
        if connection is not None:
            return self._append(connection, event)
        with self.database.transaction(immediate=True) as owned_connection:
            return self._append(owned_connection, event)

    @staticmethod
    def _append(connection: sqlite3.Connection, event: EventEnvelope) -> int:
        cursor = connection.execute(
            """
            INSERT INTO events(
              event_id, job_id, project_id, event_type, source,
              severity, occurred_at, data_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(event.event_id),
                str(event.job_id),
                str(event.project_id),
                event.event_type,
                event.source,
                event.severity,
                _utc_text(event.occurred_at),
                json.dumps(event.data, separators=(",", ":"), sort_keys=True),
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("stored event did not receive a sequence")
        return cursor.lastrowid

    def list_for_job(self, job_id: UUID, after_sequence: int = 0) -> list[StoredEvent]:
        with self.database.read_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM events
                WHERE job_id=? AND sequence>?
                ORDER BY sequence ASC
                """,
                (str(job_id), after_sequence),
            ).fetchall()
        return [_stored_event(row) for row in rows]


class AttemptRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(
        self,
        job_id: UUID,
        attempt_number: int,
        root: Path,
    ) -> JobAttemptRecord:
        attempt = JobAttemptRecord(
            attempt_id=uuid4(),
            job_id=job_id,
            attempt_number=attempt_number,
            root=root.resolve(),
        )
        started_at = _utc_text(datetime.now(UTC))
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO job_attempts(
                  attempt_id, job_id, attempt_number, status,
                  request_path, result_path, stdout_log_path, stderr_log_path, started_at
                ) VALUES (?, ?, ?, 'running', ?, ?, ?, ?, ?)
                """,
                (
                    str(attempt.attempt_id),
                    str(attempt.job_id),
                    attempt.attempt_number,
                    str(attempt.request_path),
                    str(attempt.result_path),
                    str(attempt.stdout_path),
                    str(attempt.stderr_path),
                    started_at,
                ),
            )
        return attempt

    def get(self, attempt_id: UUID) -> JobAttemptRecord | None:
        with self.database.read_connection() as connection:
            row = connection.execute(
                "SELECT * FROM job_attempts WHERE attempt_id=?",
                (str(attempt_id),),
            ).fetchone()
        if row is None:
            return None
        return JobAttemptRecord(
            attempt_id=UUID(str(row["attempt_id"])),
            job_id=UUID(str(row["job_id"])),
            attempt_number=int(row["attempt_number"]),
            root=Path(str(row["request_path"])).parent,
        )

    def latest_for_job(self, job_id: UUID) -> JobAttemptRecord | None:
        with self.database.read_connection() as connection:
            row = connection.execute(
                """
                SELECT * FROM job_attempts
                WHERE job_id=? ORDER BY attempt_number DESC LIMIT 1
                """,
                (str(job_id),),
            ).fetchone()
        if row is None:
            return None
        return JobAttemptRecord(
            attempt_id=UUID(str(row["attempt_id"])),
            job_id=UUID(str(row["job_id"])),
            attempt_number=int(row["attempt_number"]),
            root=Path(str(row["request_path"])).parent,
        )

    def finish(
        self,
        attempt_id: UUID,
        *,
        status: str,
        exit_code: int | None,
        connection: sqlite3.Connection,
    ) -> None:
        cursor = connection.execute(
            """
            UPDATE job_attempts
            SET status=?, exit_code=?, ended_at=?
            WHERE attempt_id=?
            """,
            (status, exit_code, _utc_text(datetime.now(UTC)), str(attempt_id)),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("attempt could not be finalized")


class ArtifactRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def next_version(self, project_id: UUID, logical_name: str) -> int:
        with self.database.read_connection() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(version), 0) + 1
                FROM artifacts WHERE project_id=? AND logical_name=?
                """,
                (str(project_id), logical_name),
            ).fetchone()
        return 1 if row is None else int(row[0])

    def register_verified(
        self,
        artifact: PublishedArtifact,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> ArtifactRecord:
        verified_at = datetime.now(UTC)
        if connection is not None:
            return self._register_verified(connection, artifact, verified_at)
        with self.database.transaction(immediate=True) as owned_connection:
            return self._register_verified(owned_connection, artifact, verified_at)

    @staticmethod
    def _register_verified(
        connection: sqlite3.Connection,
        artifact: PublishedArtifact,
        verified_at: datetime,
    ) -> ArtifactRecord:
        connection.execute(
            "UPDATE artifacts SET is_current=0 WHERE project_id=? AND logical_name=?",
            (str(artifact.project_id), artifact.logical_name),
        )
        connection.execute(
            """
            INSERT INTO artifacts(
              artifact_id, job_id, project_id, logical_name, kind,
              relative_path, version, size_bytes, sha256, verified_at, is_current
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                str(artifact.artifact_id),
                str(artifact.job_id),
                str(artifact.project_id),
                artifact.logical_name,
                artifact.kind,
                artifact.relative_path,
                artifact.version,
                artifact.size_bytes,
                artifact.sha256,
                _utc_text(verified_at),
            ),
        )
        row = connection.execute(
            "SELECT * FROM artifacts WHERE artifact_id=?",
            (str(artifact.artifact_id),),
        ).fetchone()
        if row is None:
            raise RuntimeError("registered artifact could not be reloaded")
        return _artifact_record(row)

    def list_for_job(self, job_id: UUID) -> list[ArtifactRecord]:
        with self.database.read_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM artifacts WHERE job_id=? ORDER BY logical_name, version",
                (str(job_id),),
            ).fetchall()
        return [_artifact_record(row) for row in rows]


class Repositories:
    def __init__(self, database: Database) -> None:
        self.jobs = JobRepository(database)
        self.events = EventRepository(database)
        self.attempts = AttemptRepository(database)
        self.artifacts = ArtifactRepository(database)


def _job_record(row: sqlite3.Row) -> JobRecord:
    return JobRecord(
        job_id=UUID(str(row["job_id"])),
        project_id=UUID(str(row["project_id"])),
        envelope=JobEnvelope.model_validate_json(str(row["request_json"])),
        status=JobStatus(str(row["status"])),
        progress=int(row["progress"]),
        current_attempt=int(row["current_attempt"]),
        next_attempt_at=_optional_datetime(row["next_attempt_at"]),
        last_error_json=(None if row["last_error_json"] is None else str(row["last_error_json"])),
        created_at=_datetime(str(row["created_at"])),
        updated_at=_datetime(str(row["updated_at"])),
    )


def _stored_event(row: sqlite3.Row) -> StoredEvent:
    envelope = EventEnvelope.model_validate(
        {
            "schema_version": "1.0",
            "event_id": row["event_id"],
            "job_id": row["job_id"],
            "project_id": row["project_id"],
            "source": row["source"],
            "event_type": row["event_type"],
            "severity": row["severity"],
            "occurred_at": row["occurred_at"],
            "data": json.loads(str(row["data_json"])),
        }
    )
    return StoredEvent(sequence=int(row["sequence"]), envelope=envelope)


def _artifact_record(row: sqlite3.Row) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=UUID(str(row["artifact_id"])),
        job_id=UUID(str(row["job_id"])),
        project_id=UUID(str(row["project_id"])),
        logical_name=str(row["logical_name"]),
        kind=str(row["kind"]),
        relative_path=str(row["relative_path"]),
        version=int(row["version"]),
        size_bytes=int(row["size_bytes"]),
        sha256=str(row["sha256"]),
        verified_at=_datetime(str(row["verified_at"])),
        is_current=bool(row["is_current"]),
    )


def _database_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return _utc_text(value)
    return value


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _optional_datetime(value: object) -> datetime | None:
    return None if value is None else _datetime(str(value))


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
