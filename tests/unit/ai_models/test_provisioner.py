import hashlib
from pathlib import Path

import pytest
from workbench.ai_models.models import LocalModelDescriptorV1, ModelFileV1
from workbench.ai_models.provisioner import LocalModelProvisioner, ModelProvisionError
from workbench.ai_models.registry import LocalModelRegistry


def descriptor(source: Path) -> LocalModelDescriptorV1:
    content = source.read_bytes()
    return LocalModelDescriptorV1(
        model_id="test-model",
        display_name="Test Model",
        kind="asr",
        engine="test",
        engine_version="1.0",
        revision="r1",
        source_ref="local:test",
        license_ref="license:test",
        files=[
            ModelFileV1(
                relative_path="model.bin",
                size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest(),
            )
        ],
        supported_devices=["cpu"],
        runtime_contract_version="1.0",
    )


def test_install_is_atomic_and_registers_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    model_file = source / "model.bin"
    model_file.write_bytes(b"model")
    registry = LocalModelRegistry(tmp_path / "settings" / "ai-models")
    provisioner = LocalModelProvisioner(tmp_path / "settings" / "ai-models", registry)

    record = provisioner.install_from_directory(descriptor(model_file), source)
    target = provisioner.model_root("test-model", "r1")
    assert record.install.status == "ready"
    assert (target / "model.bin").read_bytes() == b"model"
    assert (target / "model-manifest.json").is_file()
    downloads = tmp_path / "settings" / "ai-models" / "downloads"
    assert not any(downloads.rglob("*")) if downloads.exists() else True


def test_install_rejects_missing_declared_file(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    model_file = source / "model.bin"
    model_file.write_bytes(b"model")
    registry = LocalModelRegistry(tmp_path / "settings" / "ai-models")
    provisioner = LocalModelProvisioner(tmp_path / "settings" / "ai-models", registry)
    bad = descriptor(model_file).model_copy(
        update={
            "files": [
                ModelFileV1(
                    relative_path="missing.bin",
                    size_bytes=1,
                    sha256="0" * 64,
                )
            ]
        }
    )
    with pytest.raises(ModelProvisionError):
        provisioner.install_from_directory(bad, source)
