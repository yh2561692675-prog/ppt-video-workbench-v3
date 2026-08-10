from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from peripheral_contracts import BusinessResultManifest, JobEnvelope


def _job() -> JobEnvelope:
    from datetime import UTC, datetime

    return JobEnvelope(
        schema_version="1.0",
        job_id=uuid4(),
        project_id=uuid4(),
        job_type="document.extract",
        requested_by="test",
        idempotency_key=uuid4().hex,
        parameters={"payload_schema_version": "1.0"},
        created_at=datetime.now(UTC),
    )


def test_runtime_emits_started_progress_and_completed(tmp_path: Path, capsys) -> None:
    from workbench.business_modules.runtime import (
        BusinessExecution,
        StagedArtifact,
        execute_business_handler,
    )

    job = _job()
    result_path = tmp_path / "result.json"

    def handler(received: JobEnvelope, attempt_root: Path) -> BusinessExecution:
        assert received.job_id == job.job_id
        output = attempt_root / "extraction.json"
        output.write_text('{"page_count":8}\n', encoding="utf-8")
        business = BusinessResultManifest(
            schema_version="1.0",
            module_id="P04",
            job_type=job.job_type,
            project_id=job.project_id,
            project_revision=1,
            input_fingerprint="a" * 64,
            cache_key="b" * 64,
            result_type="document_extraction",
            payload={"page_count": 8},
        )
        return BusinessExecution(
            business_result=business,
            artifacts=(StagedArtifact("extraction", "json", output),),
        )

    execution = execute_business_handler(job, tmp_path, result_path, "P04", handler)
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert execution.outcome == "succeeded"
    assert [event["event_type"] for event in events] == [
        "module.started",
        "module.progress",
        "module.completed",
    ]
    assert result_path.is_file()
    assert (tmp_path / "business-result.json").is_file()


def test_runtime_maps_handler_exception_to_safe_failed_result(tmp_path: Path) -> None:
    from workbench.business_modules.runtime import execute_business_handler

    job = _job()

    def handler(_received: JobEnvelope, _attempt_root: Path):
        raise RuntimeError(r"C:\Users\private\secret.py Bearer token-value")

    result = execute_business_handler(job, tmp_path, tmp_path / "result.json", "P04", handler)

    assert result.outcome == "failed"
    assert result.error is not None
    assert result.error.code == "MODULE_INTERNAL_ERROR"
    assert "token-value" not in result.error.message
    assert "secret.py" not in result.error.message


def test_runtime_classifies_invalid_input_without_retry(tmp_path: Path) -> None:
    from workbench.business_modules.runtime import execute_business_handler

    def handler(_received: JobEnvelope, _attempt_root: Path):
        raise ValueError("payload is invalid")

    result = execute_business_handler(_job(), tmp_path, tmp_path / "result.json", "P04", handler)

    assert result.error is not None
    assert result.error.category.value == "INPUT"
    assert result.error.code == "MODULE_INPUT_INVALID"
    assert result.error.retryable is False
