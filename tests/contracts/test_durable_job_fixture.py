import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from workbench.domain.models import JobRecord
from workbench.jobs.contracts import JobAttemptRecord, JobCheckpointRecord


def test_durable_job_fixture_round_trips_through_strict_python_contracts() -> None:
    payload = json.loads(Path("tests/fixtures/durable-job-v1.json").read_text(encoding="utf-8"))

    job = JobRecord.model_validate(payload["job"])
    attempt = JobAttemptRecord.model_validate(payload["attempts"][0])
    checkpoint = JobCheckpointRecord.model_validate(payload["latest_checkpoint"])

    assert job.current_attempt_id == attempt.id
    assert checkpoint.attempt_id == attempt.id
    assert checkpoint.sequence == attempt.checkpoint_sequence


def test_durable_job_contract_rejects_unknown_fields() -> None:
    payload = json.loads(Path("tests/fixtures/durable-job-v1.json").read_text(encoding="utf-8"))

    with pytest.raises(ValidationError):
        JobRecord.model_validate(payload["job"] | {"unknown_field": True})
