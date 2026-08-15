from pathlib import Path

from workbench.ai_models.models import (
    LocalModelDescriptorV1,
    ModelFileV1,
    ModelRuntimeProbeV1,
)
from workbench.ai_models.registry import LocalModelRegistry


def descriptor(model_id: str = "local-asr") -> LocalModelDescriptorV1:
    return LocalModelDescriptorV1(
        model_id=model_id,
        display_name=model_id,
        kind="asr",
        engine="test",
        engine_version="1.0",
        revision="r1",
        source_ref="local:test",
        license_ref="license:test",
        files=[ModelFileV1(relative_path="model.bin", size_bytes=1, sha256="0" * 64)],
        supported_devices=["cpu"],
        runtime_contract_version="1.0",
    )


def test_registry_round_trips_and_lists_records(tmp_path: Path) -> None:
    registry = LocalModelRegistry(tmp_path / "settings" / "ai-models")
    registry.register(descriptor())
    registry.register(descriptor("local-tts"))

    reopened = LocalModelRegistry(tmp_path / "settings" / "ai-models")
    assert [item.descriptor.model_id for item in reopened.list()] == ["local-asr", "local-tts"]
    assert reopened.get("local-asr").install.status == "not_installed"


def test_registry_updates_probe(tmp_path: Path) -> None:
    registry = LocalModelRegistry(tmp_path / "settings" / "ai-models")
    registry.register(descriptor())
    record = registry.set_probe(
        ModelRuntimeProbeV1(
            model_id="local-asr",
            revision="r1",
            status="missing",
            device="unknown",
            error_code="model_manifest_invalid",
        )
    )
    assert record.last_probe is not None
    assert record.last_probe.status == "missing"
