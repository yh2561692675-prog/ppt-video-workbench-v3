# Test doubles intentionally mirror a structural runtime protocol.
# mypy cannot express that forwarding surface without obscuring the scenario.
# mypy: disable-error-code=no-untyped-def

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image
from workbench.domain.enums import JobStatus, JobType
from workbench.jobs.execution import PersistentRenderExecutionContext
from workbench.jobs.repository import JobSpec
from workbench.main import create_app
from workbench.video.models import ProjectVideoProps, VideoPageProps
from workbench.video.render_service import VideoRenderService


class ControlledInterruption(BaseException):
    """Models a process death after a durable checkpoint, not a render failure."""


class CountingRenderer:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def render(self, _props, page, _source: Path, output: Path, control=None) -> None:
        self.calls.append(page.page_order)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(f"page-{page.page_order}".encode())


class InterruptAfterFirstCheckpoint:
    def __init__(self, delegate: PersistentRenderExecutionContext) -> None:
        self.delegate = delegate
        self.checkpoint_count = 0

    @property
    def job_id(self):
        return self.delegate.job_id

    @property
    def input_fingerprint(self):
        return self.delegate.input_fingerprint

    @property
    def cancel_requested(self):
        return self.delegate.cancel_requested

    def checkpoint(self, **kwargs) -> None:
        self.delegate.checkpoint(**kwargs)
        self.checkpoint_count += 1
        if self.checkpoint_count == 1:
            raise ControlledInterruption()

    def raise_if_cancelled(self) -> None:
        self.delegate.raise_if_cancelled()

    def pause_if_requested(self) -> None:
        self.delegate.pause_if_requested()

    def heartbeat(self) -> None:
        self.delegate.heartbeat()

    def register_temporary_paths(self, paths) -> None:
        self.delegate.register_temporary_paths(paths)


def _props(project_id, root: Path) -> ProjectVideoProps:
    pages = []
    for order in (1, 2):
        source = root / f"preview-{order}.png"
        Image.new("RGB", (32, 32), (order * 20, 40, 60)).save(source)
        pages.append(
            VideoPageProps(
                page_id=uuid4(),
                page_order=order,
                title=f"page {order}",
                image_path=source.name,
                audio_path=f"audio-{order}.wav",
                start_ms=(order - 1) * 1_000,
                end_ms=order * 1_000,
            )
        )
    return ProjectVideoProps(
        project_id=project_id,
        duration_ms=2_000,
        template_version="recovery-test",
        pages=pages,
    )


def test_restart_after_first_page_checkpoint_reuses_completed_page(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    project = app.state.project_service.create("interruption recovery")
    repository = app.state.project_service.jobs
    record = repository.enqueue_or_get(
        JobSpec(
            project_id=project.id,
            job_type=JobType.EXPORT_PACKAGE,
            cache_key="controlled-interruption",
            input_fingerprint="a" * 64,
        )
    ).record
    claimed = repository.claim_next(JobType.EXPORT_PACKAGE)
    assert claimed is not None
    assert claimed.id == record.id
    root = tmp_path / project.project_dir
    renderer = CountingRenderer()
    context = PersistentRenderExecutionContext(
        job_id=record.id,
        project_dir=root,
        repository=repository,
        input_fingerprint=record.input_fingerprint,
    )
    props = _props(project.id, root)

    with pytest.raises(ControlledInterruption):
        VideoRenderService(root, renderer).render_pages(
            props, context=InterruptAfterFirstCheckpoint(context)
        )

    # The real startup recovery path converts a stranded running job to a
    # resumable state only after the checkpoint hash has been persisted.
    repository.recover_interrupted_jobs()
    interrupted = repository.get(record.id)
    assert interrupted.status is JobStatus.PAUSED
    assert interrupted.error_code == "render_worker_interrupted"
    checkpoint = PersistentRenderExecutionContext(
        job_id=record.id,
        project_dir=root,
        repository=repository,
        input_fingerprint=record.input_fingerprint,
    ).restore()
    assert checkpoint is not None
    assert checkpoint.payload["completed_pages"] == [1]

    resumed = repository.resume(record.id)
    assert resumed.id == record.id
    reclaimed = repository.claim_next(JobType.EXPORT_PACKAGE)
    assert reclaimed is not None
    assert reclaimed.id == record.id
    recovery_context = PersistentRenderExecutionContext(
        job_id=record.id,
        project_dir=root,
        repository=repository,
        input_fingerprint=record.input_fingerprint,
    )
    result = VideoRenderService(root, renderer).render_pages(props, context=recovery_context)

    assert [page.cached for page in result] == [True, False]
    assert renderer.calls == [1, 2]
