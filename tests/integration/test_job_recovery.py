from pathlib import Path
from uuid import uuid4

import pytest
from workbench.domain.enums import JobStatus, JobType
from workbench.jobs.repository import JobRepository, JobSpec
from workbench.jobs.runner import CancellationToken, JobRunner
from workbench.storage.workspace_db import WorkspaceDatabase


def repository_at(path: Path) -> JobRepository:
    database = WorkspaceDatabase(path)
    database.initialize()
    return JobRepository(database)


@pytest.mark.parametrize("progress", [0.3, 0.7])
def test_running_job_is_paused_after_process_restart(tmp_path: Path, progress: float) -> None:
    database_path = tmp_path / "workspace.db"
    first_process = repository_at(database_path)
    job_id = first_process.enqueue(
        JobSpec(project_id=uuid4(), job_type=JobType.PARSE_MATERIALS, cache_key=f"parse-{progress}")
    )
    first_process.mark_running(job_id)
    first_process.set_progress(job_id, progress)

    restarted_process = repository_at(database_path)
    recovered = restarted_process.recover_interrupted_jobs()

    assert [job.id for job in recovered] == [job_id]
    assert recovered[0].status is JobStatus.PAUSED
    assert recovered[0].progress == progress


def test_completed_job_is_reused_instead_of_enqueued_twice(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    spec = JobSpec(project_id=uuid4(), job_type=JobType.RENDER_PAGE, cache_key="render-page-1")
    original_id = repository.enqueue(spec)
    repository.mark_running(original_id)
    repository.complete(original_id)

    duplicate_id = repository.enqueue(spec)

    assert duplicate_id == original_id
    assert len(repository.list_all()) == 1
    assert repository.get(original_id).status is JobStatus.SUCCEEDED


def test_free_job_retries_with_exponential_backoff(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    job_id = repository.enqueue(
        JobSpec(project_id=uuid4(), job_type=JobType.PARSE_MATERIALS, cache_key="retry-free")
    )
    sleeps: list[float] = []
    calls = 0

    def handler() -> None:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("temporary")

    result = JobRunner(repository, sleeper=sleeps.append).execute(job_id, handler)

    assert result.status is JobStatus.SUCCEEDED
    assert result.attempts == 3
    assert sleeps == [1.0, 2.0]


def test_paid_job_stops_after_two_attempts(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    job_id = repository.enqueue(
        JobSpec(
            project_id=uuid4(),
            job_type=JobType.SYNTHESIZE_PAGE,
            cache_key="paid-page-1",
            paid=True,
        )
    )

    def failing_handler() -> None:
        raise RuntimeError("provider unavailable")

    result = JobRunner(repository, sleeper=lambda _: None).execute(job_id, failing_handler)

    assert result.status is JobStatus.FAILED
    assert result.attempts == 2
    assert result.error == "provider unavailable"


def test_cancelled_job_pauses_without_calling_handler(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    job_id = repository.enqueue(
        JobSpec(project_id=uuid4(), job_type=JobType.BUILD_SUBTITLES, cache_key="cancel")
    )
    token = CancellationToken()
    token.cancel()
    called = False

    def handler() -> None:
        nonlocal called
        called = True

    result = JobRunner(repository, sleeper=lambda _: None).execute(job_id, handler, token)

    assert result.status is JobStatus.PAUSED
    assert called is False
