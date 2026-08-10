from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from workbench.domain.enums import JobType
from workbench.jobs.checkpoint import JobContext
from workbench.jobs.repository import JobRepository, JobSpec
from workbench.jobs.runner import JobRunner
from workbench.storage.workspace_db import WorkspaceDatabase


def _repository_at(path: Path) -> JobRepository:
    database = WorkspaceDatabase(path)
    database.initialize()
    return JobRepository(database)


@pytest.mark.parametrize(
    "job_type",
    [
        JobType.PARSE_MATERIALS,
        JobType.TRANSCRIBE_AUDIO,
        JobType.SYNTHESIZE_PAGE,
        JobType.RENDER_PAGE,
        JobType.EXPORT_PACKAGE,
    ],
)
@pytest.mark.parametrize("progress", [0.3, 0.7])
def test_long_task_recovery_matrix_preserves_completed_artifacts(
    tmp_path: Path, job_type: JobType, progress: float
) -> None:
    repository = _repository_at(tmp_path / "workspace.db")
    project_dir = tmp_path / "项目"
    project_dir.mkdir()
    paid = job_type is JobType.SYNTHESIZE_PAGE
    job_id = repository.enqueue(
        JobSpec(
            project_id=uuid4(),
            job_type=job_type,
            cache_key=f"{job_type.value}-{progress}",
            paid=paid,
        )
    )
    queried_remote_ids: list[str] = []
    created_remote_ids: list[str] = []
    context = JobContext(
        job_id,
        project_dir,
        job_type,
        paid=paid,
        remote_status_lookup=lambda remote_id: queried_remote_ids.append(remote_id) or "completed",
    )
    completed_count = 1 if progress == 0.3 else 2
    completed_paths = []
    for index in range(completed_count):
        path = project_dir / "07_视频工程" / f"completed-{index}.bin"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"completed-{index}".encode())
        completed_paths.append(path)
    remote_ids = [f"heygen-task-{job_id}"] if paid else []
    context.checkpoint(
        progress,
        {
            "stage": job_type.value,
            "completed_pages": list(range(completed_count)),
            "cache_keys": [f"page-{index}" for index in range(completed_count)],
            "remote_task_ids": remote_ids,
        },
        artifacts=completed_paths,
    )
    repository.mark_running(job_id)

    restarted = _repository_at(tmp_path / "workspace.db")
    restarted.recover_interrupted_jobs()
    recovered_context = JobContext(
        job_id,
        project_dir,
        job_type,
        paid=paid,
        remote_status_lookup=lambda remote_id: queried_remote_ids.append(remote_id) or "completed",
    )

    def handler() -> None:
        restored = recovered_context.restore()
        assert restored is not None
        completed = list(restored.payload["completed_pages"])
        if paid:
            assert restored.remote_task_ids == remote_ids
            assert recovered_context.remote_status_results[remote_ids[0]] == "completed"
        for index in range(len(completed), 3):
            path = project_dir / "07_视频工程" / f"completed-{index}.bin"
            path.write_bytes(f"completed-{index}".encode())
            completed.append(index)
            recovered_context.checkpoint(
                len(completed) / 3,
                {
                    "stage": job_type.value,
                    "completed_pages": completed,
                    "remote_task_ids": remote_ids,
                },
                artifacts=[
                    project_dir / "07_视频工程" / f"completed-{item}.bin" for item in completed
                ],
            )
        if paid and recovered_context.remote_status_results[remote_ids[0]] != "completed":
            created_remote_ids.append("must-not-create")

    result = JobRunner(restarted, sleeper=lambda _: None).recover_job(
        job_id, handler, context=recovered_context
    )

    assert result.status.value == "completed"
    assert result.progress == 1.0
    assert queried_remote_ids == remote_ids if paid else queried_remote_ids == []
    assert created_remote_ids == []
    assert all(
        (project_dir / "07_视频工程" / f"completed-{index}.bin").is_file() for index in range(3)
    )
