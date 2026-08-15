from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from workbench.providers.adapter import DeterministicFakeProvider
from workbench.providers.conformance import run_adapter_conformance
from workbench.providers.models import ProviderCapabilityV1, ProviderDescriptorV1
from workbench.providers.v2 import (
    AdapterConformanceResultV1,
    ProviderOperationV2,
    ProviderRoutePolicyV2,
)

ROOT = Path(__file__).resolve().parents[2]


def _schema(name: str) -> dict[str, object]:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _descriptor() -> ProviderDescriptorV1:
    return ProviderDescriptorV1(
        provider_id="fixture-tts",
        display_name="Fixture TTS",
        kind="tts",
        adapter_version="1.0.0",
        execution_mode="in_process_builtin",
        capabilities=[
            ProviderCapabilityV1(
                capability_id="synthesize.speech",
                modalities=["audio"],
                models=["fixture-voice"],
                supports_cancellation=True,
                supports_cost_estimate=True,
            )
        ],
    )


def test_v2_schema_top_level_matches_pydantic_models() -> None:
    for filename, model in (
        ("provider-route-policy-v2.schema.json", ProviderRoutePolicyV2),
        ("provider-operation-v2.schema.json", ProviderOperationV2),
        ("provider-adapter-conformance-v1.schema.json", AdapterConformanceResultV1),
    ):
        schema = _schema(filename)
        generated = model.model_json_schema()
        assert schema["additionalProperties"] is False
        assert set(schema["properties"]) == set(generated["properties"])
        assert set(schema["required"]) == set(generated.get("required", []))


def test_route_policy_v2_is_local_first_and_rejects_restricted_remote() -> None:
    policy = ProviderRoutePolicyV2(
        policy_id="local-first",
        policy_fingerprint="sha256:" + "a" * 64,
        capability_id="synthesize.speech",
    )
    assert policy.allow_remote_https is False
    with pytest.raises(ValidationError):
        ProviderRoutePolicyV2(
            policy_id="remote-restricted",
            policy_fingerprint="sha256:" + "b" * 64,
            capability_id="synthesize.speech",
            allow_remote_https=True,
            data_classification="restricted",
        )


def test_operation_v2_blocks_unknown_billing_on_success() -> None:
    values = {
        "operation_id": uuid4(),
        "attempt_id": uuid4(),
        "idempotency_key": uuid4(),
        "provider_id": "fixture-tts",
        "capability_id": "synthesize.speech",
        "operation_kind": "tts",
        "policy_fingerprint": "sha256:" + "c" * 64,
        "expected_output_schema": "audio-wav-v1",
        "started_at": datetime.now(UTC),
    }
    with pytest.raises(ValidationError):
        ProviderOperationV2(**values, status="succeeded", billing_state="unknown")
    failed = ProviderOperationV2(**values, status="unknown_billed", billing_state="unknown")
    assert failed.status == "unknown_billed"


@pytest.mark.asyncio
async def test_fake_adapter_conformance_is_network_free() -> None:
    result = await run_adapter_conformance(DeterministicFakeProvider(_descriptor()))
    assert result.status == "pass"
    assert result.fake_provider is True
    assert set(result.checks) == {"probe", "estimate", "invoke", "cancel"}
