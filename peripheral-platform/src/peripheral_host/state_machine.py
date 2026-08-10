from __future__ import annotations

import sqlite3
from typing import Any
from uuid import UUID

from peripheral_contracts import JobStatus
from pydantic import JsonValue

from peripheral_host.events import EventFactory
from peripheral_host.repositories import JobRecord, Repositories

ALLOWED_TRANSITIONS: dict[JobStatus, frozenset[JobStatus]] = {
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.SUCCEEDED,
            JobStatus.RETRY_WAIT,
            JobStatus.FAILED,
            JobStatus.CANCELLING,
        }
    ),
    JobStatus.RETRY_WAIT: frozenset({JobStatus.QUEUED, JobStatus.CANCELLED}),
    JobStatus.CANCELLING: frozenset({JobStatus.CANCELLED}),
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.FAILED: frozenset({JobStatus.QUEUED}),
    JobStatus.CANCELLED: frozenset(),
}


TRANSITION_EVENTS: dict[tuple[JobStatus, JobStatus], str] = {
    (JobStatus.QUEUED, JobStatus.RUNNING): "job.started",
    (JobStatus.RUNNING, JobStatus.SUCCEEDED): "job.completed",
    (JobStatus.RUNNING, JobStatus.RETRY_WAIT): "job.retry_scheduled",
    (JobStatus.RUNNING, JobStatus.FAILED): "job.failed",
    (JobStatus.RUNNING, JobStatus.CANCELLING): "job.cancelling",
    (JobStatus.CANCELLING, JobStatus.CANCELLED): "job.cancelled",
    (JobStatus.QUEUED, JobStatus.CANCELLED): "job.cancelled",
    (JobStatus.RETRY_WAIT, JobStatus.QUEUED): "job.accepted",
    (JobStatus.RETRY_WAIT, JobStatus.CANCELLED): "job.cancelled",
    (JobStatus.FAILED, JobStatus.QUEUED): "job.accepted",
}


class InvalidStateTransition(ValueError):
    def __init__(self, source: JobStatus, target: JobStatus) -> None:
        super().__init__(f"invalid job transition: {source.value} -> {target.value}")
        self.source = source
        self.target = target


def can_transition(source: JobStatus, target: JobStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[source]


def require_transition(source: JobStatus, target: JobStatus) -> None:
    if not can_transition(source, target):
        raise InvalidStateTransition(source, target)


class JobStateMachine:
    def __init__(
        self,
        repositories: Repositories,
        *,
        event_factory: EventFactory | None = None,
    ) -> None:
        self.repositories = repositories
        self.event_factory = event_factory or EventFactory()

    def transition(
        self,
        job_id: UUID,
        expected: JobStatus,
        target: JobStatus,
        *,
        event_data: dict[str, JsonValue] | None = None,
        connection: sqlite3.Connection | None = None,
        **fields: Any,
    ) -> JobRecord:
        require_transition(expected, target)
        event_type = TRANSITION_EVENTS[(expected, target)]
        if connection is not None:
            return self._transition_in_transaction(
                connection,
                job_id,
                expected,
                target,
                event_type,
                event_data,
                fields,
            )
        with self.repositories.jobs.database.transaction(immediate=True) as owned_connection:
            return self._transition_in_transaction(
                owned_connection,
                job_id,
                expected,
                target,
                event_type,
                event_data,
                fields,
            )

    def _transition_in_transaction(
        self,
        connection: sqlite3.Connection,
        job_id: UUID,
        expected: JobStatus,
        target: JobStatus,
        event_type: str,
        event_data: dict[str, JsonValue] | None,
        fields: dict[str, Any],
    ) -> JobRecord:
        record = self.repositories.jobs.transition(
            job_id,
            expected,
            target,
            connection=connection,
            **fields,
        )
        data: dict[str, JsonValue] = dict(event_data or {})
        data.update({"from": expected.value, "to": target.value})
        event = self.event_factory.create(
            record=record,
            event_type=event_type,
            data=data,
        )
        self.repositories.events.append(event, connection=connection)
        return record
