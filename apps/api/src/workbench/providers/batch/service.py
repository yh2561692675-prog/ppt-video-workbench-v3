"""Policy-aware batch operations; remote execution is injected by callers."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from .models import ProviderBatchItemV1, ProviderBatchJobV1
from .repository import ProviderBatchRepository


class ProviderBatchService:
    def __init__(self, repository: ProviderBatchRepository) -> None:
        self.repository = repository

    def create(
        self,
        *,
        provider_id: str,
        operation_kind: str,
        project_id: UUID,
        revision_id: UUID,
        page_ids: list[UUID],
    ) -> ProviderBatchJobV1:
        items = [ProviderBatchItemV1(page_id=page_id) for page_id in page_ids]
        job = ProviderBatchJobV1(
            provider_id=provider_id,
            operation_kind=operation_kind,  # type: ignore[arg-type]
            project_id=project_id,
            revision_id=revision_id,
            item_ids=[item.item_id for item in items],
        )
        return self.repository.create(job, items)

    def pending_items(self, job_id: UUID) -> list[ProviderBatchItemV1]:
        return [item for item in self.repository.items(job_id) if item.status == "pending"]

    def mark_running(self, job_id: UUID, item_id: UUID) -> ProviderBatchJobV1:
        if self.repository.get(job_id).status == "unknown_billed":
            raise RuntimeError("unknown_billing_reconciliation_required")
        item = self._item(job_id, item_id)
        updated = item.model_copy(
            update={
                "status": "running",
                "attempt_count": item.attempt_count + 1,
                "updated_at": datetime.now(UTC),
            }
        )
        return self.repository.update_item(job_id, updated)

    def mark_succeeded(
        self, job_id: UUID, item_id: UUID, *, output_ref: str, request_id: str = ""
    ) -> ProviderBatchJobV1:
        item = self._item(job_id, item_id)
        updated = item.model_copy(
            update={
                "status": "succeeded",
                "output_ref": output_ref,
                "remote_request_ids": (
                    [*item.remote_request_ids, request_id]
                    if request_id
                    else item.remote_request_ids
                ),
                "updated_at": datetime.now(UTC),
            }
        )
        return self.repository.update_item(job_id, updated)

    def mark_failed(
        self, job_id: UUID, item_id: UUID, *, error_code: str, billing_unknown: bool = False
    ) -> ProviderBatchJobV1:
        item = self._item(job_id, item_id)
        updated = item.model_copy(
            update={
                "status": "unknown_billed" if billing_unknown else "failed",
                "error_code": error_code,
                "updated_at": datetime.now(UTC),
            }
        )
        return self.repository.update_item(job_id, updated)

    def resume(self, job_id: UUID) -> list[ProviderBatchItemV1]:
        job = self.repository.get(job_id)
        if job.status == "unknown_billed":
            return []
        return self.pending_items(job_id)

    def _item(self, job_id: UUID, item_id: UUID) -> ProviderBatchItemV1:
        for item in self.repository.items(job_id):
            if item.item_id == item_id:
                return item
        raise KeyError(item_id)
