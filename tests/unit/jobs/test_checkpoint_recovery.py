from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from workbench.domain.enums import JobType
from workbench.jobs.execution import PersistentRenderExecutionContext
from workbench.jobs.recovery import CheckpointRecovery
from workbench.jobs.repository import JobRepository, JobSpec
from workbench.storage.workspace_db import WorkspaceDatabase


def _context(tmp_path: Path) -> tuple[JobRepository, PersistentRenderExecutionContext]:
    database = WorkspaceDatabase(tmp_path / "workspace.db")
    database.initialize()
    repository = JobRepository(database)
    job = repository.enqueue_or_get(
        JobSpec(
            project_id=uuid4(),
            job_type=JobType.EXPORT_PACKAGE,
            cache_key="checkpoint-recovery",
            input_fingerprint="checkpoint-recovery",
            idempotency_key="checkpoint-recovery",
            payload={},
        )
    ).record
    repository.claim_next(JobType.EXPORT_PACKAGE)
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    return repository, PersistentRenderExecutionContext(
        job_id=job.id,
        project_dir=project_dir,
        repository=repository,
        input_fingerprint="checkpoint-recovery",
    )


def test_recovery_falls_back_to_last_committed_valid_checkpoint(tmp_path: Path) -> None:
    repository, context = _context(tmp_path)
    context.checkpoint(stage="first", progress=0.2, message="first checkpoint")
    context.checkpoint(stage="second", progress=0.4, message="second checkpoint")

    latest = repository.latest_checkpoint(context.job_id)
    assert latest is not None and latest.sequence == 2
    context.store.path_for(context.job_id, latest.sequence).write_text(
        "{corrupted", encoding="utf-8"
    )

    restored = CheckpointRecovery(repository, context.store).restore(context.job_id)
    assert restored is not None
    assert restored.sequence == 1
    assert restored.stage == "first"


def test_disk_checkpoint_without_database_commit_is_not_restored(tmp_path: Path) -> None:
    repository, context = _context(tmp_path)
    context.checkpoint(stage="committed", progress=0.2, message="committed checkpoint")
    orphan = context._job_context.checkpoint(  # noqa: SLF001 - simulates a DB transaction failure.
        0.4,
        {"stage": "orphan"},
    )

    restored = CheckpointRecovery(repository, context.store).restore(context.job_id)
    assert orphan.sequence == 2
    assert restored is not None
    assert restored.sequence == 1
