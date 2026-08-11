from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from fractions import Fraction
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class PresenterMediaError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PresenterMediaInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    duration_ms: int = Field(gt=0)
    container: str
    video_codec: str
    audio_codec: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0)
    sample_rate: int = Field(gt=0)
    channels: int = Field(gt=0)
    start_time_ms: int = Field(default=0, ge=0)
    time_base: str | None = None
    warnings: list[str] = Field(default_factory=list)
    raw_probe: dict[str, object] = Field(default_factory=dict)


ProbeRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def probe_presenter(
    path: Path,
    *,
    ffprobe: str = "ffprobe",
    runner: ProbeRunner | None = None,
) -> PresenterMediaInfo:
    source = path.resolve()
    if not source.is_file():
        raise PresenterMediaError("PRESENTER_SOURCE_MISSING", "presenter source does not exist")
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_streams",
        "-show_format",
        "-of",
        "json",
        str(source),
    ]
    execute = runner or _run_probe
    try:
        completed = execute(command)
    except (OSError, subprocess.SubprocessError) as error:
        raise PresenterMediaError("PRESENTER_DECODE_FAILED", str(error)) from error
    if completed.returncode != 0:
        raise PresenterMediaError(
            "PRESENTER_DECODE_FAILED", completed.stderr.strip() or "ffprobe failed"
        )
    try:
        payload = json.loads(completed.stdout)
    except (TypeError, json.JSONDecodeError) as error:
        raise PresenterMediaError("PRESENTER_DECODE_FAILED", "invalid ffprobe output") from error

    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise PresenterMediaError("PRESENTER_DECODE_FAILED", "ffprobe streams are missing")
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if video is None:
        raise PresenterMediaError("PRESENTER_DECODE_FAILED", "presenter video stream is missing")
    if audio is None:
        raise PresenterMediaError("PRESENTER_AUDIO_MISSING", "presenter audio stream is missing")

    format_payload = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    try:
        duration_ms = round(float(format_payload.get("duration", 0)) * 1_000)
        width = int(video.get("width", 0))
        height = int(video.get("height", 0))
        fps = _rate(str(video.get("avg_frame_rate", "0/1")))
        sample_rate = int(audio.get("sample_rate", 0))
        channels = int(audio.get("channels", 0))
        start_time_ms = max(0, round(float(video.get("start_time", 0)) * 1_000))
    except (TypeError, ValueError, ZeroDivisionError) as error:
        raise PresenterMediaError("PRESENTER_DECODE_FAILED", "invalid media metadata") from error
    if duration_ms <= 0:
        raise PresenterMediaError("PRESENTER_DURATION_ZERO", "presenter duration is zero")
    if min(width, height, sample_rate, channels) <= 0 or fps <= 0:
        raise PresenterMediaError("PRESENTER_DECODE_FAILED", "incomplete media metadata")

    warnings: list[str] = []
    if width < 1280 or height < 720:
        warnings.append("PRESENTER_LOW_RESOLUTION")
    nominal_rate = _rate(str(video.get("r_frame_rate", video.get("avg_frame_rate", "0/1"))))
    if abs(fps - nominal_rate) > 0.01:
        warnings.append("PRESENTER_VARIABLE_FPS")

    return PresenterMediaInfo(
        path=str(source),
        sha256=_sha256(source),
        duration_ms=duration_ms,
        container=str(format_payload.get("format_name", "")),
        video_codec=str(video.get("codec_name", "unknown")),
        audio_codec=str(audio.get("codec_name", "unknown")),
        width=width,
        height=height,
        fps=fps,
        sample_rate=sample_rate,
        channels=channels,
        start_time_ms=start_time_ms,
        time_base=str(video.get("time_base")) if video.get("time_base") else None,
        warnings=warnings,
        raw_probe=payload,
    )


def _run_probe(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)


def _rate(value: str) -> float:
    return float(Fraction(value))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
