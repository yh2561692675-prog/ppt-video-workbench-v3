from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from workbench.media.waveform import build_waveform


def _write_wave(path: Path, *, channels: int = 2, sample_rate: int = 8_000) -> None:
    frames = []
    for index in range(800):
        value = round(math.sin(2 * math.pi * index / 80) * 16_000)
        frames.extend([value] * channels)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(struct.pack(f"<{len(frames)}h", *frames))


def test_waveform_builds_deterministic_multiresolution_peak_and_rms(tmp_path: Path) -> None:
    source = tmp_path / "stereo.wav"
    _write_wave(source)

    result = build_waveform(source, source_hash="a" * 64, bucket_sizes=(100, 400))

    assert result.sample_rate == 8_000
    assert result.channels == 2
    assert result.sample_count == 800
    assert result.duration_us == 100_000
    assert [len(level.buckets) for level in result.levels] == [8, 2]
    assert 0.48 < result.levels[0].buckets[0].peak < 0.5
    assert 0.3 < result.levels[0].buckets[0].rms < 0.4
