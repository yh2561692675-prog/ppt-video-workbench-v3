from pathlib import Path
from uuid import uuid4

from workbench.domain.enums import JobStatus, JobType
from workbench.jobs.checkpoint import JobContext
from workbench.jobs.repository import JobSpec
from workbench.services.project_service import ProjectService


def test_restart_preserves_render_job_id_checkpoint_and_requires_explicit_resume(
    tmp_path: Path,
) -> None:
    service = ProjectService(tmp_path)
    project = service.create("async recovery")
    project_root = tmp_path / project.project_dir
    artifact = project_root / "08_输出" / ".render-jobs" / "job-1" / "page-0001.mp4"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"cached-page")
    job = service.jobs.enqueue_or_get(
        JobSpec(
            project_id=project.id,
            job_type=JobType.EXPORT_PACKAGE,
            cache_key=f"recovery-{uuid4()}",
            input_fingerprint="fingerprint-a",
        )
    ).record
    service.jobs.mark_running(job.id)
    service.jobs.update_progress(job.id, 0.6, stage="rendering_pages", message="第 1 页已完成")
    JobContext(job.id, project_root, JobType.EXPORT_PACKAGE).checkpoint(
        0.6,
        {"stage": "rendering_pages", "completed_pages": [1]},
        artifacts=(artifact,),
    )
    service.close()

    restarted = ProjectService(tmp_path)
    recovered = restarted.jobs.get(job.id)
    checkpoint = JobContext(job.id, project_root, JobType.EXPORT_PACKAGE).restore()
    resumed = restarted.jobs.resume(job.id)
    restarted.close()

    assert recovered.status is JobStatus.PAUSED
    assert recovered.progress == 0.6
    assert recovered.error_code == "render_worker_interrupted"
    assert checkpoint is not None
    assert checkpoint.payload["completed_pages"] == [1]
    assert resumed.id == job.id
    assert resumed.status is JobStatus.QUEUED
