from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class RenderEvidenceError(RuntimeError):
    pass


def validate_ffprobe_payload(payload: Mapping[str, Any]) -> dict[str, object]:
    streams = payload.get("streams")
    format_payload = payload.get("format")
    if not isinstance(streams, list) or not isinstance(format_payload, Mapping):
        raise RenderEvidenceError("ffprobe_payload_invalid")
    video = next(
        (
            stream
            for stream in streams
            if isinstance(stream, Mapping) and stream.get("codec_type") == "video"
        ),
        None,
    )
    audio = next(
        (
            stream
            for stream in streams
            if isinstance(stream, Mapping) and stream.get("codec_type") == "audio"
        ),
        None,
    )
    if not isinstance(video, Mapping) or video.get("codec_name") != "h264":
        raise RenderEvidenceError("video_codec_invalid")
    if not isinstance(audio, Mapping) or audio.get("codec_name") != "aac":
        raise RenderEvidenceError("audio_codec_invalid")
    duration = format_payload.get("duration")
    if not isinstance(duration, (str, int, float)):
        raise RenderEvidenceError("video_duration_invalid")
    try:
        duration_seconds = float(duration)
    except (TypeError, ValueError) as error:
        raise RenderEvidenceError("video_duration_invalid") from error
    if duration_seconds <= 0:
        raise RenderEvidenceError("video_duration_invalid")
    return {
        "duration_seconds": duration_seconds,
        "width": video.get("width"),
        "height": video.get("height"),
        "video_codec": video["codec_name"],
        "audio_codec": audio["codec_name"],
    }
