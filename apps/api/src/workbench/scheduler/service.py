from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from workbench.domain.enums import JobStatus, JobType
from workbench.jobs.repository import JobRepository, JobSpec

from .models import (
    BatchCreateRequest,
    BatchDispatchRequest,
    BatchDispatchResult,
    BatchItem,
    BatchItemStatus,
    BatchProduction,
    BatchRerunRequest,
    BatchStatus,
)


class SchedulerError(ValueError):
    pass


class SchedulerConflict(SchedulerError):
    pass


class BatchSchedulerService:
    def __init__(
        self,
        workspace_root: Path,
        project_dir_resolver: Callable[[UUID], str],
        repository: JobRepository | None = None,
        preset_exists: Callable[[str], bool] | None = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.project_dir_resolver = project_dir_resolver
        self.repository = repository
        self.preset_exists = preset_exists
        self._batches: dict[UUID, BatchProduction] = {}

    def create(self, project_id: UUID, request: BatchCreateRequest) -> BatchProduction:
        if self.preset_exists is not None:
            unknown = [preset for preset in request.preset_ids if not self.preset_exists(preset)]
            if unknown:
                raise SchedulerError(f"unknown export presets: {', '.join(unknown)}")
        items: list[BatchItem] = []
        for preset_id in request.preset_ids:
            targets: list[UUID | None] = list(request.page_ids) if request.page_ids else [None]
            for page_id in targets:
                items.append(
                    BatchItem(
                        preset_id=preset_id,
                        page_id=page_id,
                        priority=request.priority,
                        resource_cpu=min(request.resource_limits.cpu_cores, 4),
                        resource_memory_mb=min(
                            request.resource_limits.per_job_memory_mb,
                            request.resource_limits.memory_mb,
                        ),
                        resource_gpu=1 if request.resource_limits.gpu_slots else 0,
                    )
                )
        batch = BatchProduction(
            project_id=project_id,
            created_at=datetime.now(UTC).isoformat(),
            night_queue=request.night_queue,
            resource_limits=request.resource_limits,
            items=items,
        )
        batch = self._with_hash(batch)
        self._batches[batch.batch_id] = batch
        self._persist(batch)
        return batch

    def get(self, batch_id: UUID) -> BatchProduction:
        cached = self._batches.get(batch_id)
        if cached is not None:
            return cached
        for path in self._folder().glob("batch-*.json"):
            batch = BatchProduction.model_validate_json(path.read_text(encoding="utf-8"))
            if batch.batch_id == batch_id:
                self._batches[batch_id] = batch
                return batch
        raise KeyError(batch_id)

    def list_batches(self, project_id: UUID) -> list[BatchProduction]:
        return sorted(
            [batch for batch in self._all_batches() if batch.project_id == project_id],
            key=lambda item: item.created_at,
        )

    def dispatch(self, batch_id: UUID, request: BatchDispatchRequest) -> BatchDispatchResult:
        batch = self.get(batch_id)
        if batch.night_queue and not request.allow_night:
            return BatchDispatchResult(batch=batch, dispatched_item_ids=[])
        if self.repository is None:
            raise SchedulerError("job repository is not configured")
        candidate = deepcopy(batch)
        limits = candidate.resource_limits
        available_cpu = request.available_cpu or limits.cpu_cores
        available_memory = request.available_memory_mb or limits.memory_mb
        available_gpu = (
            request.available_gpu if request.available_gpu is not None else limits.gpu_slots
        )
        active = [
            item
            for item in candidate.items
            if item.status in {BatchItemStatus.DISPATCHED, BatchItemStatus.RUNNING}
        ]
        used_parallel = len(active)
        used_cpu = sum(item.resource_cpu for item in active)
        used_memory = sum(item.resource_memory_mb for item in active)
        used_gpu = sum(item.resource_gpu for item in active)
        dispatched: list[UUID] = []
        for item in sorted(
            candidate.items, key=lambda value: (-value.priority, str(value.item_id))
        ):
            if item.status is not BatchItemStatus.QUEUED:
                continue
            dependencies = {
                dependency.item_id: dependency
                for dependency in candidate.items
                if dependency.item_id in item.dependencies
            }
            if any(
                dependencies.get(dependency_id) is None
                or dependencies[dependency_id].status is not BatchItemStatus.SUCCEEDED
                for dependency_id in item.dependencies
            ):
                continue
            if used_parallel >= limits.max_parallel:
                break
            if used_cpu + item.resource_cpu > available_cpu:
                continue
            if used_memory + item.resource_memory_mb > available_memory:
                continue
            if used_gpu + item.resource_gpu > available_gpu:
                continue
            result = self.repository.enqueue_or_get(
                JobSpec(
                    project_id=candidate.project_id,
                    job_type=JobType.EXPORT_PACKAGE,
                    cache_key=f"batch:{candidate.batch_id}:{item.item_id}:{item.preset_id}",
                    idempotency_key=f"batch:{candidate.batch_id}:{item.item_id}",
                    payload={
                        "batch_id": str(candidate.batch_id),
                        "item_id": str(item.item_id),
                        "preset_id": item.preset_id,
                        "page_id": str(item.page_id) if item.page_id else None,
                        "resource_cpu": item.resource_cpu,
                        "resource_memory_mb": item.resource_memory_mb,
                        "resource_gpu": item.resource_gpu,
                    },
                    page_id=item.page_id,
                )
            )
            item.status = (
                BatchItemStatus.SUCCEEDED
                if result.record.status is JobStatus.SUCCEEDED
                else BatchItemStatus.DISPATCHED
            )
            item.job_id = result.record.id
            item.attempts += 1
            used_parallel += 1
            used_cpu += item.resource_cpu
            used_memory += item.resource_memory_mb
            used_gpu += item.resource_gpu
            dispatched.append(item.item_id)
        self._sync_status(candidate)
        self._store(candidate)
        return BatchDispatchResult(batch=candidate, dispatched_item_ids=dispatched)

    def sync(self, batch_id: UUID) -> BatchProduction:
        batch = deepcopy(self.get(batch_id))
        self._sync_status(batch)
        self._store(batch)
        return batch

    def rerun_failed(self, batch_id: UUID, request: BatchRerunRequest) -> BatchProduction:
        batch = deepcopy(self.get(batch_id))
        requested = set(request.item_ids)
        found = 0
        for item in batch.items:
            if item.item_id in requested:
                found += 1
                if item.status is not BatchItemStatus.FAILED:
                    raise SchedulerConflict(f"batch item is not failed: {item.item_id}")
                item.status = BatchItemStatus.QUEUED
                item.job_id = None
                item.error = None
        if found != len(requested):
            raise KeyError("batch item not found")
        batch.status = BatchStatus.PARTIAL
        self._store(batch)
        return batch

    def _sync_status(self, batch: BatchProduction) -> None:
        if self.repository is not None:
            for item in batch.items:
                if item.job_id is None:
                    continue
                try:
                    job = self.repository.get(item.job_id)
                except Exception:
                    continue
                mapping = {
                    JobStatus.QUEUED: BatchItemStatus.DISPATCHED,
                    JobStatus.RUNNING: BatchItemStatus.RUNNING,
                    JobStatus.SUCCEEDED: BatchItemStatus.SUCCEEDED,
                    JobStatus.FAILED: BatchItemStatus.FAILED,
                    JobStatus.CANCELLED: BatchItemStatus.CANCELLED,
                }
                item.status = mapping.get(job.status, item.status)
                if item.status is BatchItemStatus.FAILED:
                    item.error = job.error
        statuses = {item.status for item in batch.items}
        if statuses == {BatchItemStatus.SUCCEEDED}:
            batch.status = BatchStatus.SUCCEEDED
        elif BatchItemStatus.FAILED in statuses and not statuses & {
            BatchItemStatus.QUEUED,
            BatchItemStatus.DISPATCHED,
            BatchItemStatus.RUNNING,
        }:
            batch.status = BatchStatus.FAILED
        elif BatchItemStatus.RUNNING in statuses or BatchItemStatus.DISPATCHED in statuses:
            batch.status = BatchStatus.RUNNING
        elif BatchItemStatus.FAILED in statuses:
            batch.status = BatchStatus.PARTIAL

    def _all_batches(self) -> list[BatchProduction]:
        loaded = list(self._batches.values())
        known = {batch.batch_id for batch in loaded}
        for path in self._folder().glob("batch-*.json"):
            batch = BatchProduction.model_validate_json(path.read_text(encoding="utf-8"))
            if batch.batch_id not in known:
                loaded.append(batch)
        return loaded

    def _folder(self) -> Path:
        folder = self.workspace_root / "scheduler"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _persist(self, batch: BatchProduction) -> None:
        content = (batch.model_dump_json(indent=2) + "\n").encode("utf-8")
        _atomic_write(self._folder() / f"batch-{batch.batch_id}.json", content)

    def _store(self, batch: BatchProduction) -> None:
        batch.revision += 1
        batch = self._with_hash(batch)
        self._batches[batch.batch_id] = batch
        self._persist(batch)

    @staticmethod
    def _with_hash(batch: BatchProduction) -> BatchProduction:
        payload = batch.model_dump(mode="json", exclude={"content_hash"})
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        return batch.model_copy(update={"content_hash": digest})


def _atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)
