from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from workbench.domain.enums import JobStatus, JobType
from workbench.jobs.execution import (
    PersistentRenderExecutionContext,
    RenderCancelled,
    RenderPauseRequested,
)
from workbench.jobs.repository import JobRepository, JobSpec
from workbench.storage.workspace_db import WorkspaceDatabase


def setup_context(tmp_path: Path) -> tuple[JobRepository, PersistentRenderExecutionContext, str]:
    database = WorkspaceDatabase(tmp_path / "workspace.db")
    database.initialize()
    repository = JobRepository(database)
    job_id = repository.enqueue_or_get(
        JobSpec(
            project_id=uuid4(),
            job_type=JobType.EXPORT_PACKAGE,
            cache_key="execution-context",
            input_fingerprint="fingerprint-a",
            idempotency_key="execution-context",
            payload={},
        )
    ).record.id
    repository.claim_next(JobType.EXPORT_PACKAGE)
    context = PersistentRenderExecutionContext(
        job_id=job_id,
        project_dir=tmp_path / "project",
        repository=repository,
        input_fingerprint="fingerprint-a",
    )
    context.project_dir.mkdir()
    return repository, context, str(job_id)


def test_checkpoint_updates_persistent_progress_and_restores_artifact(tmp_path: Path) -> None:
    repository, context, _ = setup_context(tmp_path)
    artifact = context.project_dir / "page.mp4"
    artifact.write_bytes(b"page")

    context.checkpoint(
        stage="rendering_pages",
        progress=0.4,
        message="page 1",
        artifacts=(artifact,),
        payload={"completed_pages": [1]},
    )

    record = repository.get(context.job_id)
    assert record.progress == 0.4
    assert record.stage == "rendering_pages"
    assert record.message == "page 1"
    assert context.restore() is not None
    assert context.restore().artifacts[0].relative_path == "page.mp4"


def test_pause_is_observed_at_safe_point_and_cancel_has_precedence(tmp_path: Path) -> None:
    repository, context, _ = setup_context(tmp_path)
    repository.request_pause(context.job_id)
    with pytest.raises(RenderPauseRequested):
        context.pause_if_requested()
    assert repository.get(context.job_id).status is JobStatus.PAUSED

    repository, context, _ = setup_context(tmp_path / "cancel")
    repository.request_pause(context.job_id)
    repository.request_cancel(context.job_id)
    with pytest.raises(RenderCancelled):
        context.pause_if_requested()
    assert repository.get(context.job_id).status is JobStatus.CANCEL_REQUESTED


def test_heartbeat_delegates_to_repository(tmp_path: Path) -> None:
    repository, context, _ = setup_context(tmp_path)
    before = repository.get(context.job_id).revision
    context.heartbeat()
    assert repository.get(context.job_id).revision == before + 1
