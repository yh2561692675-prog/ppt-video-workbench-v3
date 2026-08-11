from __future__ import annotations

import hashlib
import json
import os
import subprocess
import wave
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class PresenterAudioError(RuntimeError):
    pass


class AnalysisAudio(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_path: str
    wav_path: str
    duration_ms: int = Field(gt=0)
    sample_rate: int = Field(gt=0)
    channels: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    cache_key: str
    source_time_offset_ms: int = Field(default=0, ge=0)


AudioRunner = Callable[[list[str]], subprocess.CompletedProcess[bytes]]


def extract_analysis_audio(
    source: Path,
    output: Path,
    *,
    ffmpeg: str = "ffmpeg",
    runner: AudioRunner | None = None,
    extractor_version: str = "presenter-audio-v1",
) -> AnalysisAudio:
    source_path = source.resolve()
    if not source_path.is_file():
        raise PresenterAudioError("presenter source does not exist")
    destination = output.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-i",
        str(source_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-f",
        "wav",
        "-y",
        str(temporary),
    ]
    execute = runner or _run_ffmpeg
    try:
        completed = execute(command)
        if completed.returncode != 0:
            raise PresenterAudioError("unable to extract presenter analysis audio")
        duration_ms, sample_rate, channels = _inspect_wav(temporary)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    audio_hash = _sha256(destination)
    source_hash = _sha256(source_path)
    cache_key = _digest(
        {
            "source_hash": source_hash,
            "extractor_version": extractor_version,
            "sample_rate": sample_rate,
            "channels": channels,
        }
    )
    return AnalysisAudio(
        source_path=str(source_path),
        wav_path=str(destination),
        duration_ms=duration_ms,
        sample_rate=sample_rate,
        channels=channels,
        sha256=audio_hash,
        cache_key=cache_key,
    )


def _run_ffmpeg(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, capture_output=True, check=False, timeout=3600)


def _inspect_wav(path: Path) -> tuple[int, int, int]:
    try:
        with wave.open(str(path), "rb") as handle:
            sample_rate = handle.getframerate()
            channels = handle.getnchannels()
            sample_width = handle.getsampwidth()
            frames = handle.getnframes()
    except (OSError, EOFError, wave.Error) as error:
        raise PresenterAudioError("invalid presenter analysis audio") from error
    if sample_rate != 16_000 or channels != 1 or sample_width != 2 or frames <= 0:
        raise PresenterAudioError("presenter analysis audio must be 16kHz mono PCM")
    return round(frames * 1_000 / sample_rate), sample_rate, channels


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
