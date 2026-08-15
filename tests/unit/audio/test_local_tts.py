from __future__ import annotations

import io
import wave
from pathlib import Path

import pytest
from workbench.ai_models.manifests import sha256_file
from workbench.ai_models.models import LocalModelDescriptorV1, ModelFileV1
from workbench.ai_models.provisioner import LocalModelProvisioner
from workbench.ai_models.registry import LocalModelRegistry
from workbench.ai_models.runtime import ModelRuntimeManager
from workbench.audio.local_tts import LocalSpeechSynthesizer, LocalTtsUnavailable


def _wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\0\0" * 1_600)
    return buffer.getvalue()


def test_local_tts_returns_wav_with_model_revision_and_lease_cleanup(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "model.bin").write_bytes(b"model")
    descriptor = LocalModelDescriptorV1(
        model_id="local-tts",
        display_name="Local TTS",
        kind="tts",
        engine="fixture",
        engine_version="1.0",
        revision="r1",
        source_ref="fixture",
        license_ref="internal",
        files=[
            ModelFileV1(
                relative_path="model.bin", size_bytes=5, sha256=sha256_file(source / "model.bin")
            )
        ],
        supported_devices=["cpu"],
        runtime_contract_version="1.0",
    )
    root = tmp_path / "settings" / "ai-models"
    registry = LocalModelRegistry(root)
    LocalModelProvisioner(root, registry).install_from_directory(descriptor, source)
    registry.activate("local-tts", "r1")
    runtime = ModelRuntimeManager(root, registry)
    synthesizer = LocalSpeechSynthesizer(
        runtime,
        model_id="local-tts",
        engine=lambda _text, _voice, _speed, _path: _wav(),
    )
    result = synthesizer.synthesize_result("你好", voice_id="owner")
    assert result.sample_rate == 16_000
    assert result.duration_ms == 100
    assert result.model_revision == "r1"
    assert registry.get("local-tts").install.status == "ready"


def test_local_tts_without_engine_is_explicitly_unavailable(tmp_path: Path) -> None:
    with pytest.raises(LocalTtsUnavailable, match="engine"):
        LocalSpeechSynthesizer(
            ModelRuntimeManager(tmp_path / "models", LocalModelRegistry(tmp_path / "models")),
            model_id="missing",
        ).synthesize("你好", voice_id="owner")
