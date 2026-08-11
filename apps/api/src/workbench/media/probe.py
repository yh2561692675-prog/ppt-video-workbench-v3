from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Sequence
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from fractions import Fraction
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MediaProbeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class MediaStreamProbe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=0)
    kind: str = Field(min_length=1, max_length=20)
    codec: str = Field(min_length=1, max_length=80)
    duration_us: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    fps_num: int | None = Field(default=None, gt=0)
    fps_den: int | None = Field(default=None, gt=0)
    pixel_format: str | None = Field(default=None, max_length=80)
    sample_rate: int | None = Field(default=None, gt=0)
    channels: int | None = Field(default=None, gt=0)
    language: str | None = Field(default=None, max_length=40)


class MediaProbeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    container: str = Field(min_length=1, max_length=200)
    duration_us: int = Field(ge=0)
    streams: list[MediaStreamProbe]
    tool_version: str = Field(min_length=1, max_length=200)


ProbeRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def probe_media(
    source: Path,
    *,
    ffprobe: str = "ffprobe",
    runner: ProbeRunner | None = None,
) -> MediaProbeResult:
    if not source.is_file():
        raise MediaProbeError("media_source_missing", "media source does not exist")
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(source),
    ]
    execute = runner or _run
    try:
        completed = execute(command)
    except (OSError, subprocess.SubprocessError) as error:
        raise MediaProbeError("ffprobe_unavailable", "unable to start ffprobe") from error
    if completed.returncode != 0:
        raise MediaProbeError("ffprobe_failed", completed.stderr.strip() or "ffprobe failed")
    try:
        payload = json.loads(completed.stdout)
        return _parse_payload(payload, _tool_version(ffprobe, execute))
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise MediaProbeError("ffprobe_invalid_output", "invalid ffprobe JSON output") from error


def _parse_payload(payload: object, tool_version: str) -> MediaProbeResult:
    if not isinstance(payload, dict):
        raise ValueError("probe result is not an object")
    format_data = payload.get("format")
    streams_data = payload.get("streams")
    if not isinstance(format_data, dict) or not isinstance(streams_data, list):
        raise ValueError("probe result is incomplete")
    container = str(format_data.get("format_name", ""))
    duration_us = _duration_us(format_data.get("duration"))
    streams = [_parse_stream(stream) for stream in streams_data if isinstance(stream, dict)]
    if not container or not streams:
        raise ValueError("probe result has no media streams")
    return MediaProbeResult(
        container=container,
        duration_us=duration_us,
        streams=streams,
        tool_version=tool_version,
    )


def _parse_stream(value: dict[str, Any]) -> MediaStreamProbe:
    kind = str(value.get("codec_type", ""))
    codec = str(value.get("codec_name", ""))
    if not kind or not codec:
        raise ValueError("stream codec metadata is missing")
    rate = _rate(value.get("avg_frame_rate")) if kind == "video" else None
    raw_tags = value.get("tags")
    tags: dict[str, Any] = raw_tags if isinstance(raw_tags, dict) else {}
    return MediaStreamProbe(
        index=int(value.get("index", -1)),
        kind=kind,
        codec=codec,
        duration_us=_optional_duration_us(value.get("duration")),
        width=_positive_int(value.get("width")),
        height=_positive_int(value.get("height")),
        fps_num=rate.numerator if rate is not None else None,
        fps_den=rate.denominator if rate is not None else None,
        pixel_format=_optional_text(value.get("pix_fmt")),
        sample_rate=_positive_int(value.get("sample_rate")),
        channels=_positive_int(value.get("channels")),
        language=_optional_text(tags.get("language")),
    )


def _run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=120)


def _tool_version(ffprobe: str, runner: ProbeRunner) -> str:
    try:
        completed = runner([ffprobe, "-version"])
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if completed.returncode != 0:
        return "unknown"
    return completed.stdout.splitlines()[0][:200] if completed.stdout else "unknown"


def _duration_us(value: object) -> int:
    duration = _optional_duration_us(value)
    if duration is None:
        raise ValueError("duration is missing")
    return duration


def _optional_duration_us(value: object) -> int | None:
    if value in (None, "N/A", ""):
        return None
    try:
        duration = Decimal(str(value))
    except InvalidOperation as error:
        raise ValueError("duration is invalid") from error
    if not duration.is_finite() or duration < 0:
        raise ValueError("duration is negative or non-finite")
    return int((duration * 1_000_000).to_integral_value(rounding=ROUND_HALF_UP))


def _rate(value: object) -> Fraction | None:
    if value in (None, "", "0/0", "0/1"):
        return None
    rate = Fraction(str(value))
    return rate if rate > 0 else None


def _positive_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    result = int(str(value))
    return result if result > 0 else None


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
