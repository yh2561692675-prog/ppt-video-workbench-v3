from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from workbench.contracts.p2_platform import OperationContextV1
from workbench.platform.models import (
    CapabilityStateV1,
    PlatformCapabilitySnapshotV1,
    PlatformInfoV1,
    ToolInfoV1,
)
from workbench.providers.models import (
    ProviderCapabilityV1,
    ProviderDescriptorV1,
    ProviderInvocationV1,
)

from cloud_prototype.app import SyncOperation

ROOT = Path(__file__).resolve().parents[2]


def _schema(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))


def _fixture(name: str) -> dict[str, Any]:
    path = ROOT / "tests" / "fixtures" / "p2-platform" / name
    return json.loads(path.read_text(encoding="utf-8"))


def test_cloud_schema_aliases_resolve_to_the_authoritative_cloud_directory() -> None:
    for name in ("cloud-project-revision-v1.schema.json", "cloud-sync-operation-v1.schema.json"):
        alias = _schema(name)
        assert alias["$ref"] == f"cloud/{name}"
        authoritative = _schema(f"cloud/{name}")
        assert authoritative["additionalProperties"] is False
        assert authoritative["required"]


def test_python_models_accept_versioned_golden_fixtures() -> None:
    descriptor = ProviderDescriptorV1.model_validate(_fixture("provider-descriptor-v1.json"))
    snapshot = PlatformCapabilitySnapshotV1.model_validate(
        _fixture("platform-capability-v1.json")
    )
    operation = OperationContextV1.model_validate(_fixture("operation-context-v1.json"))
    sync_operation = SyncOperation.model_validate(_fixture("cloud-sync-operation-v1.json"))
    assert descriptor.provider_id == "builtin-tts"
    assert snapshot.tools[0].executable_ref == "runtime://ffmpeg"
    assert operation.request_kind == "provider.invoke"
    assert sync_operation.kind == "project.metadata.set"


def test_contract_versioning_rejects_unknown_major_and_accepts_minor_defaults() -> None:
    fixture = _fixture("provider-descriptor-v1.json")
    ProviderDescriptorV1.model_validate({**fixture, "enabled": False})
    with pytest.raises(ValidationError):
        ProviderDescriptorV1.model_validate({**fixture, "schema_version": 2})
    with pytest.raises(ValidationError):
        ProviderDescriptorV1.model_validate({**fixture, "future_field": "rejected"})


def _assert_top_level_matches_model(schema: dict[str, Any], model: Any) -> None:
    model_schema = model.model_json_schema()
    assert set(schema["properties"]) == set(model_schema["properties"])
    expected_required = set(model_schema.get("required", []))
    if "schema_version" in schema["properties"]:
        expected_required.add("schema_version")
    assert set(schema.get("required", [])) == expected_required
    assert schema["additionalProperties"] is False


def test_provider_descriptor_schema_matches_pydantic_contract() -> None:
    schema = _schema("provider-descriptor-v1.schema.json")
    _assert_top_level_matches_model(schema, ProviderDescriptorV1)
    capability_schema = schema["$defs"]["provider_capability"]
    _assert_top_level_matches_model(capability_schema, ProviderCapabilityV1)
    assert "execution_mode" in schema["properties"]
    assert "regions" not in schema["properties"]
    assert "credential_ref" not in schema["properties"]


def test_provider_invocation_schema_matches_pydantic_contract() -> None:
    schema = _schema("provider-invocation-v1.schema.json")
    _assert_top_level_matches_model(schema, ProviderInvocationV1)
    assert schema["properties"]["operation"]["$ref"] == "operation-context-v1.schema.json"
    assert "context" not in schema["properties"]
    assert "input_sha256" not in schema["properties"]


def test_platform_snapshot_schema_matches_nested_pydantic_contracts() -> None:
    schema = _schema("platform-capability-v1.schema.json")
    _assert_top_level_matches_model(schema, PlatformCapabilitySnapshotV1)
    for key, model in {
        "platform_info": PlatformInfoV1,
        "tool": ToolInfoV1,
        "capability_state": CapabilityStateV1,
    }.items():
        _assert_top_level_matches_model(schema["$defs"][key], model)
    executable = schema["$defs"]["tool"]["properties"]["executable_ref"]
    assert "runtime" in executable["pattern"]
    assert "absolute_path" not in json.dumps(schema).lower()


def test_representative_contract_values_validate_and_preserve_logical_refs() -> None:
    descriptor = ProviderDescriptorV1(
        provider_id="builtin-tts",
        display_name="Built-in TTS",
        kind="tts",
        adapter_version="1.0.0",
        execution_mode="in_process_builtin",
        capabilities=[ProviderCapabilityV1(capability_id="tts.synthesize", modalities=["audio"])],
    )
    assert descriptor.model_validate_json(descriptor.model_dump_json()).provider_id == "builtin-tts"
    platform = PlatformCapabilitySnapshotV1(
        info=PlatformInfoV1(
            platform="windows",
            architecture="amd64",
            runtime_version="3.12",
            app_version="1.0.0",
        ),
        tools=[
            ToolInfoV1(
                name="ffmpeg",
                available=True,
                executable_ref="runtime://ffmpeg",
                source="bundled",
            )
        ],
        fingerprint="sha256:" + "0" * 64,
        generated_at="2026-08-11T00:00:00Z",
        expires_at="2026-08-11T00:15:00Z",
    )
    assert platform.tools[0].executable_ref == "runtime://ffmpeg"
    state = CapabilityStateV1(capability_id="render.local", status="supported")
    assert state.model_dump(mode="json")["status"] == "supported"


def test_platform_snapshot_rejects_expired_or_non_utc_timestamps() -> None:
    base = {
        "info": PlatformInfoV1(
            platform="linux",
            architecture="x86_64",
            runtime_version="3.12",
            app_version="1.0.0",
        ),
        "fingerprint": "sha256:" + "1" * 64,
        "generated_at": "2026-08-11T00:15:00Z",
        "expires_at": "2026-08-11T00:15:00Z",
    }
    with pytest.raises(ValidationError, match="expires_at"):
        PlatformCapabilitySnapshotV1(**base)
    with pytest.raises(ValidationError, match="UTC"):
        PlatformCapabilitySnapshotV1(
            **{**base, "expires_at": "2026-08-11T01:15:00+08:00"}
        )
