from __future__ import annotations

import math
import wave
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class WaveformError(ValueError):
    pass


class WaveformBucket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_sample: int = Field(ge=0)
    end_sample: int = Field(gt=0)
    peak: float = Field(ge=0, le=1)
    rms: float = Field(ge=0, le=1)


class WaveformLevel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    samples_per_bucket: int = Field(gt=0)
    buckets: list[WaveformBucket]


class WaveformManifestV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    sample_rate: int = Field(gt=0)
    channels: int = Field(gt=0)
    sample_count: int = Field(ge=0)
    duration_us: int = Field(ge=0)
    algorithm_version: str = "pcm-peak-rms-v1"
    levels: list[WaveformLevel]


def build_waveform(
    source: Path,
    *,
    source_hash: str,
    bucket_sizes: tuple[int, ...] = (256, 1024, 4096),
) -> WaveformManifestV1:
    if not bucket_sizes or any(size <= 0 for size in bucket_sizes):
        raise WaveformError("waveform bucket sizes must be positive")
    try:
        with wave.open(str(source), "rb") as stream:
            channels = stream.getnchannels()
            sample_width = stream.getsampwidth()
            sample_rate = stream.getframerate()
            sample_count = stream.getnframes()
            compression = stream.getcomptype()
            raw = stream.readframes(sample_count)
    except (OSError, EOFError, wave.Error) as error:
        raise WaveformError("audio source is not a readable WAV file") from error
    if compression != "NONE":
        raise WaveformError("compressed WAV input is not supported")
    if channels <= 0 or sample_rate <= 0:
        raise WaveformError("audio stream metadata is invalid")
    samples = _decode_pcm(raw, sample_width)
    expected_values = sample_count * channels
    if len(samples) != expected_values:
        raise WaveformError("audio PCM payload length does not match metadata")
    frame_peaks: list[float] = []
    frame_squares: list[float] = []
    for offset in range(0, len(samples), channels):
        frame = samples[offset : offset + channels]
        frame_peaks.append(max(abs(value) for value in frame))
        frame_squares.append(sum(value * value for value in frame) / channels)
    levels = [
        WaveformLevel(
            samples_per_bucket=size,
            buckets=_buckets(frame_peaks, frame_squares, size),
        )
        for size in sorted(set(bucket_sizes))
    ]
    return WaveformManifestV1(
        source_hash=source_hash,
        sample_rate=sample_rate,
        channels=channels,
        sample_count=sample_count,
        duration_us=round(sample_count * 1_000_000 / sample_rate),
        levels=levels,
    )


def _buckets(peaks: list[float], squares: list[float], size: int) -> list[WaveformBucket]:
    result: list[WaveformBucket] = []
    for start in range(0, len(peaks), size):
        end = min(start + size, len(peaks))
        bucket_peaks = peaks[start:end]
        bucket_squares = squares[start:end]
        result.append(
            WaveformBucket(
                start_sample=start,
                end_sample=end,
                peak=min(1.0, max(bucket_peaks, default=0.0)),
                rms=min(1.0, math.sqrt(sum(bucket_squares) / len(bucket_squares))),
            )
        )
    return result


def _decode_pcm(raw: bytes, width: int) -> list[float]:
    if width not in {1, 2, 3, 4}:
        raise WaveformError("unsupported PCM sample width")
    values: list[float] = []
    scale = float(1 << (width * 8 - 1))
    for offset in range(0, len(raw), width):
        chunk = raw[offset : offset + width]
        if len(chunk) != width:
            raise WaveformError("truncated PCM sample")
        if width == 1:
            integer = chunk[0] - 128
        else:
            integer = int.from_bytes(chunk, byteorder="little", signed=True)
        values.append(max(-1.0, min(1.0, integer / scale)))
    return values
