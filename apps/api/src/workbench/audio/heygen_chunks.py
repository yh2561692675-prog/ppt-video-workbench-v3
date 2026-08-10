from __future__ import annotations

import hashlib
import json
import os
import wave
from dataclasses import dataclass
from pathlib import Path

from workbench.audio.ffmpeg import AudioNormalizationError, NormalizedAudio, _analyze_pcm

_PREFERRED_BOUNDARIES = "。！？；"
_FALLBACK_BOUNDARIES = "，、："


@dataclass(frozen=True)
class CompletedChunk:
    index: int
    text_sha256: str
    normalized_relative_path: str
    remote_relative_path: str
    duration_ms: int
    request_id: str


def split_speech_text(text: str, max_chars: int = 60) -> list[str]:
    """Split narration into bounded chunks, preferring natural Chinese pauses."""
    if max_chars < 1:
        raise ValueError("max_chars must be positive")
    source = text.strip()
    if not source:
        return []
    parts: list[str] = []
    remainder = source
    while len(remainder) > max_chars:
        boundary = _boundary_at_or_before(remainder, max_chars)
        if boundary == 0:
            boundary = max_chars
        parts.append(remainder[:boundary])
        remainder = remainder[boundary:]
    if remainder:
        parts.append(remainder)
    return parts


def _boundary_at_or_before(text: str, limit: int) -> int:
    for boundaries in (_PREFERRED_BOUNDARIES, _FALLBACK_BOUNDARIES):
        for position in range(limit - 1, -1, -1):
            if text[position] in boundaries:
                return position + 1
    return 0


def concatenate_normalized_wavs(paths: list[Path], destination: Path) -> NormalizedAudio:
    """Join validated PCM WAV parts by copying frames, without another encode pass."""
    if not paths:
        raise AudioNormalizationError("没有可拼接的 HeyGen 音频分段")
    target = destination.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with wave.open(str(temporary), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16_000)
            for path in paths:
                with wave.open(str(path), "rb") as source:
                    if (
                        source.getnchannels(),
                        source.getsampwidth(),
                        source.getframerate(),
                        source.getcomptype(),
                    ) != (1, 2, 16_000, "NONE"):
                        raise AudioNormalizationError("HeyGen 分段音频格式不符合标准")
                    output.writeframes(source.readframes(source.getnframes()))
        quality, duration_ms, sample_rate, channels = _analyze_pcm(temporary)
        os.replace(temporary, target)
    except (OSError, EOFError, wave.Error, ValueError) as error:
        temporary.unlink(missing_ok=True)
        if isinstance(error, AudioNormalizationError):
            raise
        raise AudioNormalizationError("HeyGen 分段音频拼接失败") from error
    return NormalizedAudio(
        original_path=paths[0].resolve(),
        wav_path=target,
        duration_ms=duration_ms,
        sample_rate=sample_rate,
        channels=channels,
        sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
        quality=quality,
        command_summary="pcm wav concat -> 16000Hz/mono",
    )


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_completed_chunks(
    state_path: Path, project_dir: Path, cache_key: str, text_parts: list[str]
) -> dict[int, CompletedChunk]:
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if payload.get("schema_version") != 1 or payload.get("cache_key") != cache_key:
        return {}
    completed: dict[int, CompletedChunk] = {}
    for raw in payload.get("parts", []):
        try:
            item = CompletedChunk(
                index=int(raw["index"]),
                text_sha256=str(raw["text_sha256"]),
                normalized_relative_path=str(raw["normalized_relative_path"]),
                remote_relative_path=str(raw["remote_relative_path"]),
                duration_ms=int(raw["duration_ms"]),
                request_id=str(raw.get("request_id", "")),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if not 1 <= item.index <= len(text_parts) or item.text_sha256 != text_sha256(
            text_parts[item.index - 1]
        ):
            continue
        candidate = (project_dir / item.normalized_relative_path).resolve()
        if project_dir not in candidate.parents or not _is_normalized_wav(candidate):
            continue
        completed[item.index] = item
    return completed


def save_completed_chunks(
    state_path: Path, cache_key: str, chunks: dict[int, CompletedChunk]
) -> None:
    payload = {
        "schema_version": 1,
        "cache_key": cache_key,
        "parts": [
            {
                "index": item.index,
                "text_sha256": item.text_sha256,
                "normalized_relative_path": item.normalized_relative_path,
                "remote_relative_path": item.remote_relative_path,
                "duration_ms": item.duration_ms,
                "request_id": item.request_id,
            }
            for _, item in sorted(chunks.items())
        ],
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix(state_path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(temporary, state_path)


def _is_normalized_wav(path: Path) -> bool:
    try:
        with wave.open(str(path), "rb") as handle:
            return (
                handle.getnchannels(),
                handle.getsampwidth(),
                handle.getframerate(),
                handle.getcomptype(),
                handle.getnframes() > 0,
            ) == (1, 2, 16_000, "NONE", True)
    except (OSError, EOFError, wave.Error):
        return False
