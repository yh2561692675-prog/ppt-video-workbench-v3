from pathlib import Path

import pytest
from workbench.ai_models.manifests import sha256_file
from workbench.ai_models.models import LocalModelDescriptorV1, ModelFileV1
from workbench.ai_models.provisioner import LocalModelProvisioner
from workbench.ai_models.registry import LocalModelRegistry
from workbench.ai_models.runtime import ModelRuntimeManager, RegistryWhisperModelManager


def test_probe_and_lease_return_to_ready(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "model.bin").write_bytes(b"model")
    digest = sha256_file(source / "model.bin")
    descriptor = LocalModelDescriptorV1(
        model_id="runtime-model",
        display_name="Runtime Model",
        kind="tts",
        engine="test",
        engine_version="1.0",
        revision="r1",
        source_ref="local:test",
        license_ref="license:test",
        files=[ModelFileV1(relative_path="model.bin", size_bytes=5, sha256=digest)],
        supported_devices=["cpu"],
        runtime_contract_version="1.0",
    )
    registry = LocalModelRegistry(tmp_path / "settings" / "ai-models")
    provisioner = LocalModelProvisioner(tmp_path / "settings" / "ai-models", registry)
    provisioner.install_from_directory(descriptor, source)
    runtime = ModelRuntimeManager(tmp_path / "settings" / "ai-models", registry)

    assert runtime.probe("runtime-model").status == "available"
    with runtime.acquire("runtime-model") as lease:
        assert lease.record.install.active_lease_count == 1
        assert registry.get("runtime-model").install.status == "active"
    assert registry.get("runtime-model").install.status == "ready"


def test_probe_rejects_unsupported_device(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "model.bin").write_bytes(b"model")
    digest = sha256_file(source / "model.bin")
    descriptor = LocalModelDescriptorV1(
        model_id="cpu-model",
        display_name="CPU Model",
        kind="asr",
        engine="test",
        engine_version="1.0",
        revision="r1",
        source_ref="local:test",
        license_ref="license:test",
        files=[ModelFileV1(relative_path="model.bin", size_bytes=5, sha256=digest)],
        supported_devices=["cpu"],
        runtime_contract_version="1.0",
    )
    registry = LocalModelRegistry(tmp_path / "settings" / "ai-models")
    LocalModelProvisioner(tmp_path / "settings" / "ai-models", registry).install_from_directory(
        descriptor, source
    )
    runtime = ModelRuntimeManager(tmp_path / "settings" / "ai-models", registry)
    assert runtime.probe("cpu-model", device="cuda").status == "incompatible"
    with pytest.raises(RuntimeError, match="device_not_supported"):
        runtime.acquire("cpu-model", device="cuda")


def test_registry_manager_prefers_active_revision_and_keeps_legacy_fallback(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "model.bin").write_bytes(b"model")
    descriptor = LocalModelDescriptorV1(
        model_id="small",
        display_name="Small",
        kind="asr",
        engine="test",
        engine_version="1.0",
        revision="r1",
        source_ref="local:test",
        license_ref="license:test",
        files=[
            ModelFileV1(
                relative_path="model.bin", size_bytes=5, sha256=sha256_file(source / "model.bin")
            )
        ],
        supported_devices=["cpu"],
        runtime_contract_version="1.0",
    )
    registry = LocalModelRegistry(tmp_path / "settings" / "ai-models")
    provisioner = LocalModelProvisioner(tmp_path / "settings" / "ai-models", registry)
    provisioner.install_from_directory(descriptor, source)
    registry.activate("small", "r1")
    runtime = ModelRuntimeManager(tmp_path / "settings" / "ai-models", registry)
    manager = RegistryWhisperModelManager(tmp_path / "settings" / "asr-models", registry, runtime)
    assert manager.is_available("small") is True
    assert manager.model_path("small") == runtime.model_root("small", "r1")
    legacy = tmp_path / "settings" / "asr-models" / "legacy" / "model.bin"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"legacy")
    assert manager.is_available("legacy") is True
