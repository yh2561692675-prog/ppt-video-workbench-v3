from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from workbench.ai_models.models import (
    LocalModelDescriptorV1,
    LocalModelRecordV1,
    ModelFileV1,
    ModelInstallRecordV1,
)


def descriptor() -> LocalModelDescriptorV1:
    return LocalModelDescriptorV1(
        model_id="faster-whisper-small",
        display_name="Faster Whisper Small",
        kind="asr",
        engine="faster-whisper",
        engine_version="1.2",
        revision="main-20260815",
        source_ref="https://example.invalid/model",
        supported_languages=["zh", "en"],
        capabilities=["transcription", "word_timestamps"],
        license_ref="license:faster-whisper",
        files=[
            ModelFileV1(
                relative_path="config.json",
                size_bytes=1,
                sha256="0" * 64,
            )
        ],
        supported_devices=["cpu"],
        runtime_contract_version="1.0",
    )


def test_descriptor_rejects_absolute_or_duplicate_paths() -> None:
    with pytest.raises(ValidationError):
        ModelFileV1(relative_path="C:/model.bin", size_bytes=1, sha256="0" * 64)

    base = descriptor().model_dump()
    base["files"] = [
        {"relative_path": "model.bin", "size_bytes": 1, "sha256": "0" * 64},
        {"relative_path": "model.bin", "size_bytes": 1, "sha256": "0" * 64},
    ]
    with pytest.raises(ValidationError):
        LocalModelDescriptorV1.model_validate(base)


def test_ready_install_requires_manifest_and_install_time() -> None:
    with pytest.raises(ValidationError):
        ModelInstallRecordV1(
            model_id="model",
            revision="r1",
            status="ready",
        )

    record = ModelInstallRecordV1(
        model_id="model",
        revision="r1",
        status="ready",
        manifest_sha256="0" * 64,
        installed_at=datetime.now(UTC),
    )
    assert record.status == "ready"


def test_record_identity_is_strict() -> None:
    install = ModelInstallRecordV1(
        model_id="other",
        revision="r1",
        status="not_installed",
    )
    with pytest.raises(ValidationError):
        LocalModelRecordV1(descriptor=descriptor(), install=install)
