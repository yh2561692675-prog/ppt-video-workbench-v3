from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from PIL import Image
from workbench.contracts.p2_platform import BudgetV1, OperationContextV1
from workbench.providers.adapter import ProviderAdapterError
from workbench.providers.broker import ProviderBroker
from workbench.providers.models import ProviderDescriptorV1, ProviderInvocationV1
from workbench.providers.registry import ProviderRegistry
from workbench.providers.upstream import (
    BrokerCompletionClient,
    BrokerOcrEngine,
    BrokerPageRenderer,
    BrokerSpeechSynthesizer,
    BrokerTranscriptionBackend,
    BuiltinArtifactStore,
    BuiltinProviderAdapter,
    builtin_descriptors,
    create_llm_handler,
)


def _context() -> OperationContextV1:
    now = datetime.now(UTC)
    return OperationContextV1(
        operation_id=uuid4(),
        idempotency_key=uuid4(),
        attempt_id=uuid4(),
        tenant_id=uuid4(),
        request_kind="provider.invoke",
        started_at=now,
        deadline_at=now + timedelta(seconds=5),
        budget=BudgetV1(timeout_ms=1000, max_attempts=2),
    )


def _invocation(descriptor: ProviderDescriptorV1) -> ProviderInvocationV1:
    return ProviderInvocationV1(
        operation=_context(),
        provider_id=descriptor.provider_id,
        capability_id=descriptor.capabilities[0].capability_id,
        input_refs=["sha256:" + "a" * 64],
        expected_output_schema="provider-output-v1",
    )


def test_static_upstream_descriptors_cover_all_business_seams() -> None:
    descriptors = builtin_descriptors()
    assert {item.kind for item in descriptors} == {"llm", "asr", "tts", "avatar", "ocr", "renderer"}
    assert all(item.execution_mode == "in_process_builtin" for item in descriptors)
    assert all(item.trust == "builtin_signed" for item in descriptors)


@pytest.mark.asyncio
async def test_builtin_adapter_normalizes_outputs_without_exposing_content() -> None:
    descriptor = next(item for item in builtin_descriptors() if item.kind == "llm")
    adapter = BuiltinProviderAdapter(descriptor, lambda _: "private completion")
    invocation = _invocation(descriptor)
    result = await adapter.invoke(invocation)
    assert result.status == "succeeded"
    assert result.output_refs[0].startswith("artifact://sha256:")
    assert "private" not in str(result.model_dump())


@pytest.mark.asyncio
async def test_builtin_adapter_rejects_absolute_paths_and_normalizes_errors() -> None:
    descriptor = next(item for item in builtin_descriptors() if item.kind == "renderer")
    adapter = BuiltinProviderAdapter(descriptor, lambda _: ["C:\\secret\\out.mp4"])
    invocation = _invocation(descriptor)
    with pytest.raises(ProviderAdapterError) as raised:
        await adapter.invoke(invocation.model_copy(update={"input_refs": ["C:\\secret\\in.pptx"]}))
    error = adapter.normalize_error(raised.value, invocation)
    assert error.code == "provider.absolute_path_rejected"
    assert error.retryable is False


def test_builtin_artifact_store_is_bounded_and_keeps_logical_references() -> None:
    store = BuiltinArtifactStore(max_entries=1, max_bytes=32)
    first = store.put("first")
    assert first.startswith("artifact://sha256:")
    assert store.get(first) == "first"
    second = store.put("second")
    with pytest.raises(ProviderAdapterError):
        store.get(first)
    assert store.get(second) == "second"


def test_llm_handler_resolves_profile_credentials_without_contract_secrets() -> None:
    descriptor = next(item for item in builtin_descriptors() if item.kind == "llm")
    invocation = _invocation(descriptor).model_copy(
        update={
            "model": "test-model",
            "parameters": {
                "llm.profile_id": str(uuid4()),
                "llm.messages": [{"role": "user", "content": "hello"}],
                "llm.max_tokens": 8,
            },
        }
    )
    calls: list[dict[str, object]] = []

    class Profiles:
        def credentials(self, profile_id: UUID) -> object:
            return SimpleNamespace(
                profile=SimpleNamespace(base_url="https://example.test", model="profile-model"),
                api_key="secret-value",
            )

    class Client:
        def complete(self, **kwargs: object) -> str:
            calls.append(kwargs)
            return "safe completion"

    value = create_llm_handler(Client(), Profiles())(invocation)
    assert value == "safe completion"
    assert calls[0]["api_key"] == "secret-value"
    assert "secret-value" not in str(invocation.model_dump())


def test_broker_completion_client_reads_text_from_local_artifact_bridge() -> None:
    descriptor = next(item for item in builtin_descriptors() if item.kind == "llm")
    artifacts = BuiltinArtifactStore()
    adapter = BuiltinProviderAdapter(
        descriptor,
        lambda _: "broker completion",
        artifact_store=artifacts,
    )
    broker = ProviderBroker(ProviderRegistry([descriptor]), {descriptor.provider_id: adapter})
    client = BrokerCompletionClient(
        broker,
        artifacts,
        tenant_id=uuid4(),
        profile_id=uuid4(),
    )
    assert client.complete(
        base_url="ignored",
        api_key="ignored",
        model="stable",
        messages=[{"role": "user", "content": "hello"}],
    ) == "broker completion"


def _broker_with_handlers(artifacts: BuiltinArtifactStore) -> ProviderBroker:
    descriptors = builtin_descriptors()

    def handler(invocation: ProviderInvocationV1) -> object:
        if invocation.provider_id == "builtin-asr":
            return json.dumps(
                {
                    "language": "zh",
                    "segments": [
                        {
                            "start": 0,
                            "end": 1,
                            "text": "你好",
                            "words": [
                                {"text": "你好", "start": 0, "end": 1, "probability": 0.99}
                            ],
                        }
                    ],
                }
            )
        if invocation.provider_id == "builtin-ocr":
            return json.dumps([{"text": "标题", "bbox": [0, 0, 10, 10], "confidence": 0.9}])
        if invocation.provider_id == "builtin-renderer":
            return b"rendered"
        if invocation.provider_id in {"builtin-tts", "builtin-avatar"}:
            return b"speech"
        return "unused"

    adapters = {
        descriptor.provider_id: BuiltinProviderAdapter(
            descriptor, handler, artifact_store=artifacts
        )
        for descriptor in descriptors
    }
    return ProviderBroker(ProviderRegistry(descriptors), adapters)


def test_broker_upstream_facades_preserve_asr_ocr_speech_and_renderer_contracts(
    tmp_path: Path,
) -> None:
    artifacts = BuiltinArtifactStore()
    broker = _broker_with_handlers(artifacts)
    tenant_id = uuid4()

    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    segments, language = BrokerTranscriptionBackend(
        broker, artifacts, tenant_id=tenant_id
    ).transcribe(audio, language="zh", device="cpu")
    segment = list(segments)[0]
    assert language == "zh"
    assert segment.text == "你好"

    ocr = BrokerOcrEngine(broker, artifacts, tenant_id=tenant_id)
    assert ocr.recognize(Image.new("RGB", (10, 10)))[0].text == "标题"

    assert BrokerSpeechSynthesizer(
        broker, artifacts, tenant_id=tenant_id, kind="tts"
    ).synthesize("你好", voice_id="voice-1") == b"speech"
    assert BrokerSpeechSynthesizer(
        broker, artifacts, tenant_id=tenant_id, kind="avatar"
    ).synthesize("你好", voice_id="voice-1") == b"speech"

    props = SimpleNamespace(model_dump=lambda **_: {"project_id": "p"})
    page = SimpleNamespace(model_dump=lambda **_: {"page_order": 1})
    source = tmp_path / "source.png"
    source.write_bytes(b"source")
    output = tmp_path / "out.mp4"
    BrokerPageRenderer(broker, artifacts, tenant_id=tenant_id).render(
        props, page, source, output
    )
    assert output.read_bytes() == b"rendered"
