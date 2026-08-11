import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
from workbench.jobs.handlers.presenter import (
    PRESENTER_PIPELINE_STAGES,
    PresenterPipelineHandler,
    PresenterPipelineInterrupted,
)


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("failure_stage", ["asr_30", "asr_70", "match_50", "page_render_50"])
def test_presenter_pipeline_recovers_from_latest_safe_boundary(
    tmp_path: Path, failure_stage: str
) -> None:
    project = tmp_path / "presenter-project"
    project.mkdir()
    source = project / "source.mp4"
    source.write_bytes(b"immutable presenter source")
    locks = project / "manual-locks.json"
    locks.write_bytes(b'{"page-1":true}')
    source_hash = _hash(source)
    lock_hash = _hash(locks)
    job_id = uuid4()
    first_handler = PresenterPipelineHandler(project, job_id)
    first_processed: list[str] = []

    def first_processor(stage: str) -> list[Path]:
        first_processed.append(stage)
        return [first_handler.write_artifact(f"pipeline/{stage}.bin", stage.encode())]

    with pytest.raises(PresenterPipelineInterrupted, match=failure_stage):
        first_handler.run(
            first_processor,
            protected_artifacts=[source, locks],
            manual_lock_ids=["page-1"],
            interrupt_after=failure_stage,
        )

    recovered_handler = PresenterPipelineHandler(project, job_id)
    resumed_processed: list[str] = []

    def resumed_processor(stage: str) -> list[Path]:
        resumed_processed.append(stage)
        return [recovered_handler.write_artifact(f"pipeline/{stage}.bin", stage.encode())]

    final = recovered_handler.run(
        resumed_processor,
        protected_artifacts=[source, locks],
        manual_lock_ids=["page-1"],
    )

    completed_index = PRESENTER_PIPELINE_STAGES.index(failure_stage)
    assert resumed_processed == list(PRESENTER_PIPELINE_STAGES[completed_index + 1 :])
    assert final.completed_stages == list(PRESENTER_PIPELINE_STAGES)
    assert final.preserve_manual_locks is True
    assert final.payload["manual_lock_ids"] == ["page-1"]
    assert _hash(source) == source_hash
    assert _hash(locks) == lock_hash
