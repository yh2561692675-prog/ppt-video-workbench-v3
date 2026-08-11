from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from workbench.contracts.p2_platform import (
    BudgetV1,
    LogicalResourceRefV1,
    OperationContextV1,
    StructuredErrorV1,
    canonical_json,
    canonical_sha256,
)


def _id() -> UUID:
    return uuid4()


def test_operation_context_has_distinct_operation_id_idempotency_and_attempt() -> None:
    now = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)
    context = OperationContextV1(
        operation_id=_id(),
        idempotency_key=_id(),
        attempt_id=_id(),
        tenant_id=_id(),
        request_kind="provider.invoke",
        started_at=now,
        deadline_at=now.replace(minute=5),
        budget=BudgetV1(timeout_ms=30_000),
    )
    assert context.schema_version == 1
    assert context.model_dump(mode="json")["started_at"] == "2026-08-11T08:00:00Z"


@pytest.mark.parametrize(
    "path",
    [
        "C:/Users/secret.pptx",
        "/home/user/secret.pptx",
        "materials/../secret.pptx",
        "materials\\secret.pptx",
        "materials/\x00x",
    ],
)
def test_logical_resource_ref_rejects_absolute_or_unsafe_paths(path: str) -> None:
    with pytest.raises(ValidationError):
        LogicalResourceRefV1(
            tenant_id=_id(), resource_type="project", resource_id=_id(), logical_path=path
        )


def test_canonical_json_is_order_and_unicode_stable() -> None:
    left = {"z": "\u00e9", "a": {"b": 2, "a": 1}}
    right = {"a": {"a": 1, "b": 2}, "z": "e\u0301"}
    assert canonical_json(left) == canonical_json(right)
    assert canonical_sha256(left) == canonical_sha256(right)
    assert canonical_json(left) == '{"a":{"a":1,"b":2},"z":"' + "\u00e9" + '"}'


def test_canonical_json_rejects_non_finite_values() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        canonical_json({"value": float("nan")})


def test_structured_error_forbids_arbitrary_nested_details() -> None:
    with pytest.raises(ValidationError):
        StructuredErrorV1(
            code="provider.timeout",
            category="provider",
            message="Provider timed out",
            retryable=True,
            failover_allowed=True,
            user_action="Retry",
            safe_details={"nested": {"secret": "no"}},
            operation_id=_id(),
        )


def test_contract_json_has_no_credentials_or_absolute_path_fields() -> None:
    payload = OperationContextV1(
        operation_id=_id(),
        idempotency_key=_id(),
        attempt_id=_id(),
        tenant_id=_id(),
        request_kind="sync.append",
        started_at=datetime(2026, 8, 11, 8, 0, tzinfo=UTC),
        budget=BudgetV1(timeout_ms=10_000),
    ).model_dump(mode="json")
    encoded = json.dumps(payload)
    assert "credential" not in encoded.lower()
    assert "absolute_path" not in encoded.lower()
