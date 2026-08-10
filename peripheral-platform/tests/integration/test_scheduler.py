from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from threading import Thread

from peripheral_contracts import ActionRequest, ActionType, JobEnvelope, JobStatus


def _mode(job: JobEnvelope, fail_mode: str, *, delay_ms: int = 0) -> JobEnvelope:
    return job.model_copy(
        update={
            "parameters": {
                "text": "scheduled echo",
                "fail_mode": fail_mode,
                "delay_ms": delay_ms,
            }
        }
    )


def test_scheduler_runs_one_queued_job_to_success(scheduler_bundle, job: JobEnvelope):
    scheduler, service, _, _ = scheduler_bundle
    submitted = service.submit_job(_mode(job, "none"))

    assert scheduler.run_once() is True

    assert service.get_job_status(submitted.job_id).status is JobStatus.SUCCEEDED


def test_retryable_failure_uses_bounded_backoff(scheduler_bundle, job: JobEnvelope):
    scheduler, service, _, clock = scheduler_bundle
    submitted = service.submit_job(_mode(job, "retryable"))

    scheduler.run_once()
    status = service.get_job_status(submitted.job_id)

    assert status.status is JobStatus.RETRY_WAIT
    assert status.next_attempt_at == clock.now() + timedelta(seconds=5)
    assert status.attempt_count == 1


def test_third_retryable_failure_becomes_terminal(scheduler_bundle, job: JobEnvelope):
    scheduler, service, _, clock = scheduler_bundle
    submitted = service.submit_job(_mode(job, "retryable"))

    scheduler.run_once()
    clock.advance(5)
    scheduler.run_once()
    clock.advance(30)
    scheduler.run_once()

    status = service.get_job_status(submitted.job_id)
    assert status.status is JobStatus.FAILED
    assert status.attempt_count == 3


def test_permanent_failure_does_not_retry(scheduler_bundle, job: JobEnvelope):
    scheduler, service, _, _ = scheduler_bundle
    submitted = service.submit_job(_mode(job, "permanent"))

    scheduler.run_once()

    assert service.get_job_status(submitted.job_id).status is JobStatus.FAILED


def test_running_cancel_terminates_module(scheduler_bundle, job: JobEnvelope):
    scheduler, service, _, _ = scheduler_bundle
    submitted = service.submit_job(_mode(job, "none", delay_ms=5000))
    worker = Thread(target=scheduler.run_once, daemon=True)
    worker.start()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if service.get_job_status(submitted.job_id).status is JobStatus.RUNNING:
            break
        time.sleep(0.02)
    action = ActionRequest(
        schema_version="1.0",
        action=ActionType.CANCEL,
        requested_by="workbench",
        requested_at=datetime.now(UTC),
    )

    service.request_action(submitted.job_id, action)
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert service.get_job_status(submitted.job_id).status is JobStatus.CANCELLED
