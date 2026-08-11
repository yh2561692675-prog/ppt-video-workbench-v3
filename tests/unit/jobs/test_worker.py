from __future__ import annotations

from pathlib import Path
from threading import Event, Lock
from time import monotonic, sleep
from uuid import uuid4

from workbench.domain.enums import JobStatus, JobType
from workbench.jobs.repository import JobRepository, JobSpec
from workbench.jobs.worker import RenderJobWorker
from workbench.storage.workspace_db import WorkspaceDatabase


def repository_at(path: Path) -> JobRepository:
    database = WorkspaceDatabase(path)
    database.initialize()
    return JobRepository(database)


def submit(repository: JobRepository, project_id=None):
    project_id = project_id or uuid4()
    return repository.enqueue_or_get(
        JobSpec(
            project_id=project_id,
            job_type=JobType.EXPORT_PACKAGE,
            cache_key=f"worker:{uuid4().hex}",
            input_fingerprint=uuid4().hex,
            idempotency_key=uuid4().hex,
            payload={},
        )
    ).record


def wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = monotonic() + timeout
    while not predicate() and monotonic() < deadline:
        sleep(0.01)
    assert predicate()


def test_worker_runs_queued_handler_after_wake(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    record = submit(repository)
    called = Event()

    def handler(job) -> None:
        assert job.id == record.id
        called.set()
        repository.succeed(job.id, {"ok": True})

    worker = RenderJobWorker(repository, handler, poll_interval=0.01)
    worker.start()
    worker.wake()
    wait_until(called.is_set)
    worker.stop()

    assert repository.get(record.id).status is JobStatus.SUCCEEDED
    assert not worker.is_alive


def test_worker_is_single_consumer_and_continues_after_handler_failure(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    first = submit(repository)
    second = submit(repository)
    lock = Lock()
    active = 0
    maximum = 0
    completed = Event()
    calls: list[str] = []

    def handler(job) -> None:
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
            calls.append(str(job.id))
        try:
            if job.id == first.id:
                raise RuntimeError("temporary failure")
            repository.succeed(job.id, {"ok": True})
            completed.set()
        finally:
            with lock:
                active -= 1

    worker = RenderJobWorker(repository, handler, poll_interval=0.01)
    worker.start()
    worker.wake()
    wait_until(completed.is_set)
    worker.stop()

    assert maximum == 1
    assert calls == [str(first.id), str(second.id)]
    assert repository.get(first.id).status is JobStatus.FAILED
    assert repository.get(second.id).status is JobStatus.SUCCEEDED


def test_worker_stop_requests_pause_for_active_job(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    record = submit(repository)
    entered = Event()
    release = Event()

    def handler(job) -> None:
        entered.set()
        release.wait(2.0)

    worker = RenderJobWorker(repository, handler, poll_interval=0.01)
    worker.start()
    worker.wake()
    wait_until(entered.is_set)
    worker.stop(timeout=0.01)
    assert repository.get(record.id).status is JobStatus.PAUSE_REQUESTED
    release.set()
    worker.stop(timeout=2.0)


def test_worker_round_robins_registered_job_types(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    project_id = uuid4()
    export = submit(repository, project_id)
    preview = repository.enqueue_or_get(
        JobSpec(
            project_id=project_id,
            job_type=JobType.RENDER_PREVIEW,
            cache_key=f"preview:{uuid4().hex}",
            input_fingerprint=uuid4().hex,
            idempotency_key=uuid4().hex,
        )
    ).record
    completed = Event()
    calls: list[JobType] = []

    def handle(job) -> None:
        calls.append(job.job_type)
        repository.succeed(job.id, {"ok": True})
        if len(calls) == 2:
            completed.set()

    registry = {
        JobType.EXPORT_PACKAGE: handle,
        JobType.RENDER_PREVIEW: handle,
    }
    worker = RenderJobWorker(
        repository,
        handlers=registry,
        job_types=(JobType.EXPORT_PACKAGE, JobType.RENDER_PREVIEW),
        poll_interval=0.01,
    )
    worker.start()
    worker.wake()
    wait_until(completed.is_set)
    worker.stop()

    assert set(calls) == {JobType.EXPORT_PACKAGE, JobType.RENDER_PREVIEW}
    assert repository.get(export.id).status is JobStatus.SUCCEEDED
    assert repository.get(preview.id).status is JobStatus.SUCCEEDED
