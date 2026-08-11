from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from workbench.domain.enums import JobStatus
from workbench.scheduler.models import BatchCreateRequest, BatchDispatchRequest, BatchRerunRequest
from workbench.scheduler.service import BatchSchedulerService, SchedulerConflict


class FakeRepository:
    def __init__(self) -> None:
        self.jobs = {}

    def enqueue_or_get(self, spec):
        job_id = uuid4()
        record = SimpleNamespace(id=job_id, status=JobStatus.QUEUED, error=None)
        self.jobs[job_id] = record
        return SimpleNamespace(record=record, created=True)

    def get(self, job_id):
        return self.jobs[job_id]


def test_create_dispatch_and_resource_limit(tmp_path):
    repository = FakeRepository()
    project_id = uuid4()
    service = BatchSchedulerService(
        tmp_path,
        project_dir_resolver=lambda _: "project",
        repository=repository,
        preset_exists=lambda value: value in {"master-1080p-30", "douyin-square-1080p-30"},
    )
    batch = service.create(
        project_id,
        BatchCreateRequest(
            preset_ids=["master-1080p-30", "douyin-square-1080p-30"],
            resource_limits={
                "max_parallel": 1,
                "cpu_cores": 2,
                "memory_mb": 4096,
                "gpu_slots": 0,
                "per_job_memory_mb": 2048,
            },
        ),
    )
    result = service.dispatch(batch.batch_id, BatchDispatchRequest())
    assert len(result.dispatched_item_ids) == 1
    assert sum(item.status.value == "dispatched" for item in result.batch.items) == 1


def test_night_queue_and_unknown_preset_are_gated(tmp_path):
    service = BatchSchedulerService(
        tmp_path,
        project_dir_resolver=lambda _: "project",
        repository=FakeRepository(),
        preset_exists=lambda value: value == "master-1080p-30",
    )
    with pytest.raises(ValueError, match="unknown export presets"):
        service.create(uuid4(), BatchCreateRequest(preset_ids=["bad"]))
    batch = service.create(
        uuid4(), BatchCreateRequest(preset_ids=["master-1080p-30"], night_queue=True)
    )
    result = service.dispatch(batch.batch_id, BatchDispatchRequest(allow_night=False))
    assert result.dispatched_item_ids == []


def test_failed_item_can_be_rerun(tmp_path):
    repository = FakeRepository()
    service = BatchSchedulerService(
        tmp_path,
        project_dir_resolver=lambda _: "project",
        repository=repository,
        preset_exists=lambda _: True,
    )
    batch = service.create(uuid4(), BatchCreateRequest(preset_ids=["preset"]))
    dispatched = service.dispatch(batch.batch_id, BatchDispatchRequest()).batch
    job_id = dispatched.items[0].job_id
    repository.jobs[job_id].status = JobStatus.FAILED
    failed = service.sync(batch.batch_id)
    assert failed.items[0].status.value == "failed"
    rerun = service.rerun_failed(
        batch.batch_id, BatchRerunRequest(item_ids=[failed.items[0].item_id])
    )
    assert rerun.items[0].status.value == "queued"
    with pytest.raises(SchedulerConflict):
        service.rerun_failed(batch.batch_id, BatchRerunRequest(item_ids=[failed.items[0].item_id]))
