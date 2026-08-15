from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from workbench.providers.batch import ProviderBatchRepository, ProviderBatchService


def test_batch_resumes_pending_items_and_blocks_unknown_billed_retry(tmp_path: Path) -> None:
    repository = ProviderBatchRepository(tmp_path / "batches")
    service = ProviderBatchService(repository)
    page_ids = [uuid4(), uuid4(), uuid4()]
    job = service.create(
        provider_id="heygen",
        operation_kind="tts",
        project_id=uuid4(),
        revision_id=uuid4(),
        page_ids=page_ids,
    )
    first, second, third = [item.item_id for item in repository.items(job.job_id)]
    service.mark_running(job.job_id, first)
    service.mark_succeeded(job.job_id, first, output_ref="asset:one", request_id="req-1")
    service.mark_failed(job.job_id, second, error_code="remote_timeout", billing_unknown=True)
    current = repository.get(job.job_id)
    assert current.status == "unknown_billed"
    assert service.resume(job.job_id) == []
    assert third in [item.item_id for item in repository.items(job.job_id)]

    restarted = ProviderBatchService(ProviderBatchRepository(tmp_path / "batches"))
    assert restarted.resume(job.job_id) == []
