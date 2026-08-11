from pathlib import Path
from uuid import uuid4

import pytest
from workbench.domain.enums import AttemptStatus, JobStatus, JobType
from workbench.jobs.checkpoint import JobContext
from workbench.jobs.repository import JobRepository, JobSpec
from workbench.jobs.runner import CancellationToken, JobRunner
from workbench.services.project_service import ProjectService
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
    assert recovered[0].error_code == "render_worker_interrupted"


def test_restart_expires_the_interrupted_attempt_before_resume(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    job = repository.enqueue_or_get(
        JobSpec(project_id=uuid4(), job_type=JobType.RENDER_PREVIEW, cache_key="preview-recovery")
    ).record
    claimed = repository.claim_next(JobType.RENDER_PREVIEW)
    assert claimed is not None
    previous_attempt = repository.current_attempt(job.id)
    assert previous_attempt is not None

    repository.recover_interrupted_jobs()

    assert repository.current_attempt(job.id).status is AttemptStatus.EXPIRED
    resumed = repository.resume(job.id)
    assert resumed.status is JobStatus.QUEUED
    next_claim = repository.claim_next(JobType.RENDER_PREVIEW)
    assert next_claim is not None
    assert repository.current_attempt(job.id).generation == previous_attempt.generation + 1


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


def test_paid_unknown_remote_result_requires_explicit_confirmation_before_retry(
    tmp_path: Path,
) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    job_id = repository.enqueue(
        JobSpec(
            project_id=uuid4(),
            job_type=JobType.SYNTHESIZE_PAGE,
            cache_key="paid-unknown-remote-result",
            paid=True,
        )
    )
    context = JobContext(
        job_id,
        tmp_path / "project",
        JobType.SYNTHESIZE_PAGE,
        paid=True,
        remote_status_lookup=lambda _: None,
    )
    context.checkpoint(0.1, {"remote_task_ids": ["provider-task-1"]})
    called = False

    def handler() -> None:
        nonlocal called
        called = True

    paused_for_review = JobRunner(repository, sleeper=lambda _: None).recover_job(
        job_id, handler, context=context
    )

    assert paused_for_review.status is JobStatus.NEEDS_CONFIRMATION
    assert paused_for_review.error_code == "paid_remote_result_unknown"
    assert called is False
    retried = repository.confirm_paid_retry(
        job_id, expected_revision=paused_for_review.revision
    )
    assert retried.status is JobStatus.QUEUED


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


def test_restart_cleans_registered_cancelled_render_temporary_paths(tmp_path: Path) -> None:
    service = ProjectService(tmp_path)
    project = service.create("cancel cleanup")
    project_root = tmp_path / project.project_dir
    temporary = project_root / "08_输出" / ".render-jobs" / "job-temp"
    temporary.mkdir(parents=True)
    (temporary / "partial.mp4").write_bytes(b"partial")
    job = service.jobs.enqueue_or_get(
        JobSpec(
            project_id=project.id,
            job_type=JobType.EXPORT_PACKAGE,
            cache_key="cancel-cleanup",
        )
    ).record
    service.jobs.mark_running(job.id)
    JobContext(job.id, project_root, JobType.EXPORT_PACKAGE).checkpoint(
        0.5,
        {
            "stage": "rendering_pages",
            "temporary_paths": ["08_输出/.render-jobs/job-temp"],
        },
    )
    service.jobs.request_cancel(job.id)
    service.close()

    restarted = ProjectService(tmp_path)
    recovered = restarted.jobs.get(job.id)
    restarted.close()

    assert recovered.status is JobStatus.CANCELLED
    assert recovered.error_code == "render_cancelled"
    assert not temporary.exists()


def test_cancel_cleanup_failure_is_persisted_as_stable_error_code(tmp_path: Path) -> None:
    repository = repository_at(tmp_path / "workspace.db")
    job = repository.enqueue_or_get(
        JobSpec(
            project_id=uuid4(),
            job_type=JobType.EXPORT_PACKAGE,
            cache_key="cleanup-failure",
        )
    ).record
    repository.mark_running(job.id)
    repository.request_cancel(job.id)

    recovered = repository.recover_interrupted_jobs(
        lambda _: (_ for _ in ()).throw(OSError("locked"))
    )

    assert recovered[0].status is JobStatus.FAILED
    assert recovered[0].error_code == "render_cancel_cleanup_failed"
