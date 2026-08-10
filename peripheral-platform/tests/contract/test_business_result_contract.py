from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError


def valid_business_result() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "module_id": "P04",
        "job_type": "document.extract",
        "project_id": str(uuid4()),
        "project_revision": 12,
        "input_fingerprint": "a" * 64,
        "cache_key": "b" * 64,
        "result_type": "document_extraction",
        "payload": {"page_count": 8},
        "artifacts": [
            {
                "logical_name": "extraction",
                "kind": "json",
                "size_bytes": 12,
                "sha256": "c" * 64,
            }
        ],
    }


def test_business_result_rejects_unknown_fields_and_bad_hash() -> None:
    from peripheral_contracts import BusinessResultManifest

    base = valid_business_result()
    with pytest.raises(ValidationError):
        BusinessResultManifest.model_validate({**base, "unexpected": True})

    base["input_fingerprint"] = "bad"
    with pytest.raises(ValidationError):
        BusinessResultManifest.model_validate(base)


def test_business_result_requires_matching_project_and_job_identity() -> None:
    from peripheral_contracts import BusinessResultManifest

    result = BusinessResultManifest.model_validate(valid_business_result())
    assert result.schema_version == "1.0"
    assert result.module_id == "P04"
    assert result.result_type == "document_extraction"
