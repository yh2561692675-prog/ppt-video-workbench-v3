from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from peripheral_contracts import (
    ErrorCategory,
    ErrorDetail,
    EventEnvelope,
    JobEnvelope,
    JobResult,
    UnsupportedSchemaVersion,
)
from pydantic import ValidationError


@pytest.fixture
def valid_job_dict() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "job_id": str(uuid4()),
        "project_id": str(uuid4()),
        "job_type": "system.echo",
        "requested_by": "workbench",
        "priority": 50,
        "idempotency_key": "0123456789abcdef",
        "inputs": [],
        "parameters": {"text": "contract check"},
        "created_at": datetime.now(UTC).isoformat(),
    }


@pytest.fixture
def valid_event_dict(valid_job_dict: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "event_id": str(uuid4()),
        "job_id": valid_job_dict["job_id"],
        "project_id": valid_job_dict["project_id"],
        "source": "echo",
        "event_type": "module.started",
        "severity": "info",
        "occurred_at": datetime.now(UTC).isoformat(),
        "data": {"attempt": 1},
    }


def test_job_envelope_rejects_unknown_major_version(valid_job_dict):
    valid_job_dict["schema_version"] = "2.0"

    with pytest.raises(UnsupportedSchemaVersion):
        JobEnvelope.model_validate(valid_job_dict)


def test_job_envelope_rejects_unknown_fields(valid_job_dict):
    valid_job_dict["unexpected"] = True

    with pytest.raises(ValidationError):
        JobEnvelope.model_validate(valid_job_dict)


def test_event_payload_is_json_object(valid_event_dict):
    valid_event_dict["data"] = ["not", "an", "object"]

    with pytest.raises(ValidationError):
        EventEnvelope.model_validate(valid_event_dict)


def test_failed_result_requires_error_detail(valid_job_dict):
    with pytest.raises(ValidationError, match="failed result requires error"):
        JobResult.model_validate(
            {
                "schema_version": "1.0",
                "job_id": valid_job_dict["job_id"],
                "outcome": "failed",
                "outputs": [],
            }
        )


def test_succeeded_result_rejects_error_detail(valid_job_dict):
    error = ErrorDetail(
        category=ErrorCategory.INPUT,
        code="INVALID_INPUT",
        message="Input is invalid",
        retryable=False,
    )

    with pytest.raises(ValidationError, match="succeeded result cannot contain error"):
        JobResult.model_validate(
            {
                "schema_version": "1.0",
                "job_id": valid_job_dict["job_id"],
                "outcome": "succeeded",
                "outputs": [],
                "error": error.model_dump(mode="json"),
            }
        )
