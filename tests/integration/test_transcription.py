from __future__ import annotations

import json
import wave
from collections.abc import Iterable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from workbench.audio.models import (
    RecognizedSegment,
    RecognizedWord,
    WhisperModelManager,
)
from workbench.audio.transcriber import (
    ModelUnavailable,
    PauseController,
    Transcriber,
    TranscriptionError,
    TranscriptionPaused,
    available_transcription_devices,
    write_transcript,
)
from workbench.main import create_app


class FakeBackend:
    def __init__(
        self,
        segments: list[RecognizedSegment],
        *,
        controller: PauseController | None = None,
    ) -> None:
        self.segments = segments
        self.controller = controller
        self.calls: list[dict[str, object]] = []

    def transcribe(self, _: Path, **kwargs: object) -> tuple[Iterable[RecognizedSegment], str]:
        self.calls.append(kwargs)

        def generate() -> Iterable[RecognizedSegment]:
            for index, segment in enumerate(self.segments):
                yield segment
                if index == 0 and self.controller is not None:
                    self.controller.request_pause()

        return generate(), "zh"


def _segment(text: str, start: float, end: float, probability: float = 0.98) -> RecognizedSegment:
    return RecognizedSegment(
        start=start,
        end=end,
        text=text,
        words=[RecognizedWord(text=text, start=start, end=end, probability=probability)],
    )


def _installed_manager(tmp_path: Path) -> WhisperModelManager:
    manager = WhisperModelManager(tmp_path / "models")
    model_path = manager.model_path("small")
    model_path.mkdir(parents=True, exist_ok=True)
    (model_path / "model.bin").write_bytes(b"fixture")
    return manager


def test_uses_small_cpu_int8_and_emits_monotonic_word_timestamps(tmp_path: Path) -> None:
    backend = FakeBackend([_segment("你好", 0.0, 0.4), _segment("世界", 0.5, 0.9)])
    transcriber = Transcriber(_installed_manager(tmp_path), backend)

    transcript = transcriber.transcribe(tmp_path / "recording.wav")

    assert transcript.model == "small"
    assert transcript.detected_language == "zh"
    assert [word.text for word in transcript.words] == ["你好", "世界"]
    assert [word.start_ms for word in transcript.words] == [0, 500]
    assert backend.calls == [
        {
            "model_path": _installed_manager(tmp_path).model_path("small"),
            "language": "zh",
            "device": "cpu",
            "compute_type": "int8",
            "word_timestamps": True,
        }
    ]


def test_detects_cuda_and_preserves_transcript_structure_when_selected(tmp_path: Path) -> None:
    assert available_transcription_devices(lambda: 1) == ["cpu", "cuda"]
    backend = FakeBackend([_segment("加速转写", 0.0, 0.5)])

    transcript = Transcriber(_installed_manager(tmp_path), backend).transcribe(
        tmp_path / "recording.wav", device="cuda"
    )

    assert transcript.device == "cuda"
    assert transcript.words[0].text == "加速转写"
    assert backend.calls[0]["compute_type"] == "float16"


def test_missing_model_is_actionable_and_model_download_resumes(tmp_path: Path) -> None:
    manager = WhisperModelManager(tmp_path / "models")
    with pytest.raises(ModelUnavailable, match="small"):
        Transcriber(manager, FakeBackend([])).transcribe(tmp_path / "recording.wav")

    progress: list[tuple[int, int]] = []
    part = manager.download_path("small")
    part.parent.mkdir(parents=True)
    part.write_bytes(b"abc")
    offsets: list[int] = []

    def chunks(offset: int) -> Iterable[bytes]:
        offsets.append(offset)
        yield b"def"
        yield b"ghi"

    installed = manager.download(
        "small",
        total_bytes=9,
        chunks=chunks,
        progress=lambda done, total: progress.append((done, total)),
    )

    assert offsets == [3]
    assert installed.read_bytes() == b"abcdefghi"
    assert progress[-1] == (9, 9)
    assert manager.is_available("small")


def test_pause_checkpoint_resumes_without_duplicate_segments(tmp_path: Path) -> None:
    controller = PauseController()
    segments = [_segment("第一句", 0.0, 0.5), _segment("第二句", 0.6, 1.0)]
    backend = FakeBackend(segments, controller=controller)
    transcriber = Transcriber(_installed_manager(tmp_path), backend)
    checkpoint = tmp_path / "checkpoint.json"

    with pytest.raises(TranscriptionPaused):
        transcriber.transcribe(
            tmp_path / "recording.wav", controller=controller, checkpoint=checkpoint
        )
    assert json.loads(checkpoint.read_text(encoding="utf-8"))["completed_segments"] == 1

    controller.resume()
    resumed = Transcriber(_installed_manager(tmp_path), FakeBackend(segments)).transcribe(
        tmp_path / "recording.wav", controller=controller, checkpoint=checkpoint
    )
    assert [segment.text for segment in resumed.segments] == ["第一句", "第二句"]
    assert not checkpoint.exists()


@pytest.mark.parametrize("segments", [[], [_segment("短", 0.0, 0.08)]])
def test_silence_and_short_audio_return_valid_structure(
    tmp_path: Path, segments: list[RecognizedSegment]
) -> None:
    transcript = Transcriber(_installed_manager(tmp_path), FakeBackend(segments)).transcribe(
        tmp_path / "recording.wav"
    )
    assert len(transcript.segments) == len(segments)


def test_rejects_non_monotonic_word_timestamps(tmp_path: Path) -> None:
    backend = FakeBackend([_segment("后", 1.0, 1.2), _segment("前", 0.5, 0.8)])
    with pytest.raises(TranscriptionError, match="单调"):
        Transcriber(_installed_manager(tmp_path), backend).transcribe(tmp_path / "recording.wav")


def test_writes_transcript_to_fixed_project_artifact(tmp_path: Path) -> None:
    transcript = Transcriber(
        _installed_manager(tmp_path), FakeBackend([_segment("测试", 0.0, 0.4)])
    ).transcribe(tmp_path / "recording.wav")
    artifact = write_transcript(transcript, tmp_path / "project")
    assert artifact == tmp_path / "project" / "05_音频" / "音频转写.json"
    assert json.loads(artifact.read_text(encoding="utf-8"))["words"][0]["text"] == "测试"


def test_transcription_api_uses_imported_audio_and_persists_project_state(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    model = workspace / "settings" / "asr-models" / "small" / "model.bin"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"fixture")
    backend = FakeBackend([_segment("本地转写", 0.0, 0.5)])
    app = create_app(workspace, transcription_backend=backend)
    fixture = tmp_path / "voice.wav"
    with wave.open(str(fixture), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\0\0" * 1_600)

    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "转写项目"}).json()["data"]
        imported = client.post(
            f"/api/projects/{project['id']}/audio/import",
            files={"file": ("voice.wav", fixture.read_bytes(), "audio/wav")},
        )
        assert imported.status_code == 201
        devices = client.get(f"/api/projects/{project['id']}/audio/transcription-devices")
        assert devices.status_code == 200
        assert devices.json()["data"][0] == "cpu"
        response = client.post(
            f"/api/projects/{project['id']}/audio/transcribe", json={"device": "cpu"}
        )
        assert response.status_code == 201
        assert response.json()["data"]["words"][0]["text"] == "本地转写"
        reopened = client.get(f"/api/projects/{project['id']}").json()["data"]
        assert reopened["transcript"]["model"] == "small"
        artifact = workspace / reopened["project_dir"] / "05_音频" / "音频转写.json"
        assert artifact.exists()
