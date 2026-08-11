from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError
from workbench.assets.derivative_models import (
    DerivativeOperation,
    DerivativeRequestV1,
    derivative_fingerprint,
)


def request() -> DerivativeRequestV1:
    return DerivativeRequestV1(
        parent_asset_id=uuid4(),
        parent_revision=3,
        parent_content_hash="a" * 64,
        operation=DerivativeOperation.PROXY,
        parameters={"width": 960, "codec": "h264"},
        output_slot="preview",
        tool_fingerprint="b" * 64,
    )


def test_derivative_fingerprint_is_deterministic_for_equivalent_parameters() -> None:
    first = request()
    second = first.model_copy(update={"parameters": {"codec": "h264", "width": 960}})

    assert derivative_fingerprint(first) == derivative_fingerprint(second)
    assert first.fingerprint == second.fingerprint


def test_derivative_contract_rejects_extra_fields_and_path_like_output_slots() -> None:
    payload = request().model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        DerivativeRequestV1.model_validate(payload)

    with pytest.raises(ValidationError, match="single relative identifier"):
        DerivativeRequestV1.model_validate(
            request().model_dump(mode="json") | {"output_slot": "../preview"}
        )

    with pytest.raises(ValidationError):
        DerivativeRequestV1.model_validate(
            request().model_dump(mode="json") | {"schema_version": "2.0"}
        )
