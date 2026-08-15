"""Atomic JSON persistence for provider batches."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from uuid import UUID

from .models import ProviderBatchItemV1, ProviderBatchJobV1


class ProviderBatchRepositoryError(RuntimeError):
    pass


class ProviderBatchRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "batches.json"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._jobs: dict[str, ProviderBatchJobV1] = {}
        self._items: dict[str, ProviderBatchItemV1] = {}
        self._load()

    def create(
        self, job: ProviderBatchJobV1, items: list[ProviderBatchItemV1]
    ) -> ProviderBatchJobV1:
        with self._lock:
            if str(job.job_id) in self._jobs:
                raise ProviderBatchRepositoryError("batch_exists")
            if (
                len(items) != len(job.item_ids)
                or {item.item_id for item in items} != set(job.item_ids)
            ):
                raise ProviderBatchRepositoryError("batch_items_mismatch")
            self._jobs[str(job.job_id)] = job
            self._items.update({str(item.item_id): item for item in items})
            self._save()
            return job

    def get(self, job_id: UUID) -> ProviderBatchJobV1:
        try:
            return self._jobs[str(job_id)]
        except KeyError as error:
            raise ProviderBatchRepositoryError("batch_not_found") from error

    def items(self, job_id: UUID) -> list[ProviderBatchItemV1]:
        job = self.get(job_id)
        return [self._items[str(item_id)] for item_id in job.item_ids]

    def update_item(self, job_id: UUID, item: ProviderBatchItemV1) -> ProviderBatchJobV1:
        with self._lock:
            job = self.get(job_id)
            if item.item_id not in job.item_ids:
                raise ProviderBatchRepositoryError("item_not_in_batch")
            self._items[str(item.item_id)] = item
            items = self.items(job_id)
            unknown = [part.item_id for part in items if part.status == "unknown_billed"]
            if unknown:
                status = "unknown_billed"
            elif all(part.status == "succeeded" for part in items):
                status = "succeeded"
            elif any(part.status == "failed" for part in items):
                status = "failed"
            elif any(part.status == "running" for part in items):
                status = "running"
            else:
                status = "paused"
            updated = job.model_copy(
                update={
                    "status": status,
                    "updated_at": item.updated_at,
                    "unknown_billed_item_ids": unknown,
                    "last_error_code": item.error_code,
                }
            )
            self._jobs[str(job_id)] = updated
            self._save()
            return updated

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self._jobs = {
                item["job_id"]: ProviderBatchJobV1.model_validate(item)
                for item in payload.get("jobs", [])
            }
            self._items = {
                item["item_id"]: ProviderBatchItemV1.model_validate(item)
                for item in payload.get("items", [])
            }
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise ProviderBatchRepositoryError("batch_repository_corrupt") from error

    def _save(self) -> None:
        payload = {
            "schema_version": 1,
            "jobs": [item.model_dump(mode="json") for item in self._jobs.values()],
            "items": [item.model_dump(mode="json") for item in self._items.values()],
        }
        fd, raw_path = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.root)
        temp_path = Path(raw_path)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
