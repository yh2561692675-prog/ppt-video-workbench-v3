from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Protocol

from workbench.audio.models import (
    RecognizedSegment,
    RecognizedWord,
    Transcript,
    TranscriptSegment,
    TranscriptWord,
    WhisperModelManager,
)


class ModelUnavailable(RuntimeError):
    pass


class TranscriptionError(RuntimeError):
    pass


class TranscriptionPaused(RuntimeError):
    pass


def available_transcription_devices(
    cuda_device_count: Callable[[], int] | None = None,
) -> list[str]:
    if cuda_device_count is None:
        try:
            import ctranslate2  # type: ignore[import-untyped]
        except ImportError:
            return ["cpu"]
        cuda_device_count = ctranslate2.get_cuda_device_count
    try:
        has_cuda = cuda_device_count() > 0
    except (OSError, RuntimeError):
        has_cuda = False
    return ["cpu", "cuda"] if has_cuda else ["cpu"]


class TranscriptionBackend(Protocol):
    def transcribe(
        self,
        audio: Path,
        **kwargs: object,
    ) -> tuple[Iterable[RecognizedSegment], str]: ...


class PauseController:
    def __init__(self) -> None:
        self._paused = False

    def request_pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    @property
    def paused(self) -> bool:
        return self._paused


class FasterWhisperBackend:
    requires_local_model = True

    def transcribe(self, audio: Path, **kwargs: object) -> tuple[Iterable[RecognizedSegment], str]:
        try:
            from faster_whisper import WhisperModel  # type: ignore[import-untyped]
        except ImportError as error:
            raise ModelUnavailable("faster-whisper 运行时尚未安装") from error
        model = WhisperModel(
            str(kwargs["model_path"]),
            device=str(kwargs["device"]),
            compute_type=str(kwargs["compute_type"]),
        )
        raw_segments, info = model.transcribe(
            str(audio),
            language=str(kwargs["language"]),
            word_timestamps=bool(kwargs["word_timestamps"]),
        )

        def converted() -> Iterable[RecognizedSegment]:
            for segment in raw_segments:
                words = [
                    RecognizedWord(
                        text=word.word,
                        start=float(word.start),
                        end=float(word.end),
                        probability=float(word.probability),
                    )
                    for word in (segment.words or [])
                ]
                yield RecognizedSegment(
                    start=float(segment.start),
                    end=float(segment.end),
                    text=str(segment.text),
                    words=words,
                )

        return converted(), str(info.language)


class Transcriber:
    def __init__(
        self,
        models: WhisperModelManager,
        backend: TranscriptionBackend | None = None,
        *,
        model: str = "small",
    ) -> None:
        self.models = models
        self.backend = backend or FasterWhisperBackend()
        self.model = model

    def transcribe(
        self,
        audio: Path,
        language: str = "zh",
        *,
        device: str = "cpu",
        controller: PauseController | None = None,
        checkpoint: Path | None = None,
    ) -> Transcript:
        if getattr(self.backend, "requires_local_model", True) and not self.models.is_available(
            self.model
        ):
            raise ModelUnavailable(f"本地语音模型 {self.model} 尚未下载")
        compute_type = "int8" if device == "cpu" else "float16"
        raw_segments, detected_language = self.backend.transcribe(
            audio,
            model_path=self.models.model_path(self.model),
            language=language,
            device=device,
            compute_type=compute_type,
            word_timestamps=True,
        )
        completed = _load_checkpoint(checkpoint)
        segment_records = list(completed)
        completed_count = len(completed)
        for index, segment in enumerate(raw_segments):
            if index < completed_count:
                continue
            if controller is not None and controller.paused:
                _write_checkpoint(checkpoint, segment_records)
                raise TranscriptionPaused("转写已暂停，可从检查点继续")
            segment_records.append(_convert_segment(segment))
        words = [word for segment in segment_records for word in segment.words]
        _validate_monotonic(words)
        if checkpoint is not None:
            checkpoint.unlink(missing_ok=True)
        return Transcript(
            segments=segment_records,
            words=words,
            detected_language=detected_language,
            model=self.model,
            device=device,
        )


def write_transcript(transcript: Transcript, project_dir: Path) -> Path:
    target = project_dir / "05_音频" / "音频转写.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(transcript.model_dump(mode="json"), handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    return target


def _convert_segment(segment: RecognizedSegment) -> TranscriptSegment:
    return TranscriptSegment(
        text=segment.text,
        start_ms=max(0, round(segment.start * 1000)),
        end_ms=max(0, round(segment.end * 1000)),
        words=[
            TranscriptWord(
                text=word.text,
                start_ms=max(0, round(word.start * 1000)),
                end_ms=max(0, round(word.end * 1000)),
                confidence=word.probability,
            )
            for word in segment.words
        ],
    )


def _validate_monotonic(words: list[TranscriptWord]) -> None:
    previous_end = 0
    for word in words:
        if word.end_ms < word.start_ms or word.start_ms < previous_end:
            raise TranscriptionError("词级时间戳必须单调且不得重叠")
        previous_end = word.end_ms


def _load_checkpoint(path: Path | None) -> list[TranscriptSegment]:
    if path is None or not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [TranscriptSegment.model_validate(item) for item in payload.get("segments", [])]


def _write_checkpoint(path: Path | None, segments: list[TranscriptSegment]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "completed_segments": len(segments),
        "segments": [item.model_dump(mode="json") for item in segments],
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
