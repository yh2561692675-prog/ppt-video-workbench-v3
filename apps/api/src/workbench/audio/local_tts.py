"""Bridge for local TTS engines managed by the AI model center.

The engine callable is injected by the runtime package, which keeps the base
video workflow usable when no optional local TTS engine is installed.
"""

from __future__ import annotations

import hashlib
import io
import wave
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from workbench.ai_models.runtime import ModelRuntimeManager


class LocalTtsUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class LocalSpeechResult:
    audio: bytes
    sample_rate: int
    channels: int
    duration_ms: int
    content_sha256: str
    model_id: str
    model_revision: str


class LocalSpeechSynthesizer:
    def __init__(
        self,
        runtime: ModelRuntimeManager,
        *,
        model_id: str,
        engine: Callable[[str, str, float, Path], bytes] | None = None,
    ) -> None:
        self.runtime = runtime
        self.model_id = model_id
        self.engine = engine

    def synthesize_result(
        self,
        text: str,
        *,
        voice_id: str,
        language: str = "zh",
        speed: float = 1.0,
        device: str = "cpu",
    ) -> LocalSpeechResult:
        if not text.strip():
            raise ValueError("text must not be blank")
        if not 0.5 <= speed <= 2.0:
            raise ValueError("speed must be between 0.5 and 2.0")
        if self.engine is None:
            raise LocalTtsUnavailable("local_tts_engine_unavailable")
        try:
            lease_context = self.runtime.acquire(self.model_id, device=device)
        except (KeyError, RuntimeError) as error:
            raise LocalTtsUnavailable("local_tts_model_unavailable") from error
        with lease_context as lease:
            payload = self.engine(
                text,
                voice_id,
                speed,
                self.runtime.model_root(
                    lease.record.descriptor.model_id, lease.record.descriptor.revision
                ),
            )
            result = _validate_wav(payload)
            return LocalSpeechResult(
                audio=payload,
                sample_rate=result[0],
                channels=result[1],
                duration_ms=result[2],
                content_sha256=hashlib.sha256(payload).hexdigest(),
                model_id=lease.record.descriptor.model_id,
                model_revision=lease.record.descriptor.revision,
            )

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str,
        language: str = "zh",
        speed: float = 1.0,
    ) -> bytes:
        return self.synthesize_result(
            text, voice_id=voice_id, language=language, speed=speed
        ).audio


def _validate_wav(payload: bytes) -> tuple[int, int, int]:
    try:
        with wave.open(io.BytesIO(payload), "rb") as handle:
            if handle.getcomptype() != "NONE" or handle.getsampwidth() != 2:
                raise LocalTtsUnavailable("local_tts_output_format_invalid")
            frames = handle.getnframes()
            if frames <= 0:
                raise LocalTtsUnavailable("local_tts_output_empty")
            duration_ms = round(frames * 1000 / handle.getframerate())
            return handle.getframerate(), handle.getnchannels(), duration_ms
    except (EOFError, wave.Error) as error:
        raise LocalTtsUnavailable("local_tts_output_not_wav") from error
