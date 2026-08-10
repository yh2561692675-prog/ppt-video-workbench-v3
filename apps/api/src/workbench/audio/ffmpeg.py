from __future__ import annotations

import hashlib
import math
import os
import struct
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path


class AudioNormalizationError(ValueError):
    pass


@dataclass(frozen=True)
class AudioQuality:
    peak_dbfs: float
    silence_ratio: float
    silence_intervals_ms: list[tuple[int, int]]
    needs_confirmation: bool


@dataclass(frozen=True)
class NormalizedAudio:
    original_path: Path
    wav_path: Path
    duration_ms: int
    sample_rate: int
    channels: int
    sha256: str
    quality: AudioQuality
    command_summary: str


def normalize_audio(path: Path, output_dir: Path | None = None) -> NormalizedAudio:
    source = path.resolve()
    if not source.is_file():
        raise AudioNormalizationError("音频文件不存在")
    destination_dir = (output_dir or source.parent / "normalized").resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{source.stem}.normalized.wav"
    temporary = destination.with_suffix(".wav.tmp")
    temporary.unlink(missing_ok=True)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-i",
        str(source),
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
    try:
        completed = subprocess.run(command, capture_output=True, check=False, timeout=3600)
    except (OSError, subprocess.TimeoutExpired) as error:
        temporary.unlink(missing_ok=True)
        raise AudioNormalizationError("无法启动 FFmpeg 或转换超时") from error
    if completed.returncode != 0:
        temporary.unlink(missing_ok=True)
        raise AudioNormalizationError("无法读取或转换音频")
    try:
        quality, duration_ms, sample_rate, channels = _analyze_pcm(temporary)
    except (OSError, EOFError, wave.Error, ValueError) as error:
        temporary.unlink(missing_ok=True)
        raise AudioNormalizationError("规范化音频校验失败") from error
    os.replace(temporary, destination)
    return NormalizedAudio(
        original_path=source,
        wav_path=destination,
        duration_ms=duration_ms,
        sample_rate=sample_rate,
        channels=channels,
        sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
        quality=quality,
        command_summary="ffmpeg normalize -> pcm_s16le/16000Hz/mono",
    )


def _analyze_pcm(path: Path) -> tuple[AudioQuality, int, int, int]:
    with wave.open(str(path), "rb") as handle:
        sample_rate = handle.getframerate()
        channels = handle.getnchannels()
        sample_width = handle.getsampwidth()
        frame_count = handle.getnframes()
        if sample_rate != 16_000 or channels != 1 or sample_width != 2 or frame_count <= 0:
            raise ValueError("unexpected normalized audio format")
        samples = struct.unpack(f"<{frame_count}h", handle.readframes(frame_count))
    duration_ms = round(frame_count * 1000 / sample_rate)
    peak = max(abs(value) for value in samples)
    peak_dbfs = -96.0 if peak == 0 else 20 * math.log10(peak / 32767)
    window_frames = max(1, sample_rate // 100)  # 10 ms
    silence_limit = round(32767 * 10 ** (-45 / 20))
    silent_windows: list[bool] = []
    for start in range(0, frame_count, window_frames):
        window = samples[start : start + window_frames]
        silent_windows.append(max((abs(value) for value in window), default=0) <= silence_limit)
    silence_intervals = _intervals(silent_windows, duration_ms)
    silent_ms = sum(end - start for start, end in silence_intervals)
    ratio = min(1.0, silent_ms / duration_ms) if duration_ms else 1.0
    return (
        AudioQuality(
            peak_dbfs=round(peak_dbfs, 2),
            silence_ratio=round(ratio, 4),
            silence_intervals_ms=silence_intervals,
            needs_confirmation=ratio >= 0.4 or peak_dbfs <= -45,
        ),
        duration_ms,
        sample_rate,
        channels,
    )


def _intervals(windows: list[bool], duration_ms: int) -> list[tuple[int, int]]:
    intervals: list[tuple[int, int]] = []
    start: int | None = None
    for index, silent in enumerate(windows):
        if silent and start is None:
            start = index * 10
        if not silent and start is not None:
            intervals.append((start, min(index * 10, duration_ms)))
            start = None
    if start is not None:
        intervals.append((start, duration_ms))
    return intervals
