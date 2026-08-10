from __future__ import annotations

from peripheral_contracts import JobEnvelope, JobStatus


def test_startup_recovers_orphaned_running_job(scheduler_bundle, job: JobEnvelope):
    scheduler, service, _, clock = scheduler_bundle
    submitted = service.submit_job(job)
    claimed = service.claim_next(clock.now())
    assert claimed is not None
    assert claimed.status is JobStatus.RUNNING

    count = scheduler.recover_on_startup()

    assert count == 1
    recovered = service.get_job_status(submitted.job_id)
    assert recovered.status is JobStatus.RETRY_WAIT
    assert recovered.next_attempt_at == clock.now()
