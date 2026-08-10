from __future__ import annotations

import sqlite3
from uuid import UUID, uuid4

import pytest
from peripheral_contracts import EventEnvelope, JobEnvelope, JobStatus
from peripheral_host.events import EventFactory
from peripheral_host.repositories import Repositories
from peripheral_host.state_machine import InvalidStateTransition, JobStateMachine


def test_transition_updates_state_and_appends_matching_event(
    repositories: Repositories,
    job: JobEnvelope,
):
    repositories.jobs.create(job)
    machine = JobStateMachine(repositories)

    updated = machine.transition(job.job_id, JobStatus.QUEUED, JobStatus.RUNNING)
    stored = repositories.events.list_for_job(job.job_id)

    assert updated.status is JobStatus.RUNNING
    assert [event.envelope.event_type for event in stored] == ["job.started"]
    assert stored[0].envelope.data == {"from": "queued", "to": "running"}


def test_invalid_transition_writes_neither_state_nor_event(
    repositories: Repositories,
    job: JobEnvelope,
):
    repositories.jobs.create(job)
    machine = JobStateMachine(repositories)

    with pytest.raises(InvalidStateTransition):
        machine.transition(job.job_id, JobStatus.QUEUED, JobStatus.SUCCEEDED)

    assert repositories.jobs.get(job.job_id).status is JobStatus.QUEUED
    assert repositories.events.list_for_job(job.job_id) == []


def test_event_insert_failure_rolls_back_state_change(
    repositories: Repositories,
    job: JobEnvelope,
):
    repositories.jobs.create(job)
    duplicate_event_id = uuid4()
    factory = EventFactory(event_id_factory=lambda: duplicate_event_id)
    repositories.events.append(
        factory.create(
            record=repositories.jobs.get(job.job_id),
            event_type="job.accepted",
            data={"progress": 0},
        )
    )
    machine = JobStateMachine(repositories, event_factory=factory)

    with pytest.raises(sqlite3.IntegrityError):
        machine.transition(job.job_id, JobStatus.QUEUED, JobStatus.RUNNING)

    assert repositories.jobs.get(job.job_id).status is JobStatus.QUEUED
    assert len(repositories.events.list_for_job(job.job_id)) == 1


def _event_job_id(event: EventEnvelope) -> UUID:
    return event.job_id


def test_event_factory_uses_job_identity(repositories: Repositories, job: JobEnvelope):
    record = repositories.jobs.create(job)

    event = EventFactory().create(
        record=record,
        event_type="job.accepted",
        data={"progress": 0},
    )

    assert _event_job_id(event) == job.job_id
    assert event.project_id == job.project_id
