from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))


def test_playback_probe_requires_real_zero_to_ended_event_sequence() -> None:
    from scripts.windows_acceptance.playback import validate_playback_evidence

    metrics = validate_playback_evidence(
        {
            "events": [
                {"event": "play", "current_time": 0},
                {"event": "timeupdate", "current_time": 2.5},
                {"event": "ended", "current_time": 5},
            ],
            "console_errors": [],
            "failed_requests": [],
            "screenshots": ["start.png", "middle.png", "end.png"],
        }
    )

    assert metrics["duration_seconds"] == 5
    assert metrics["stall_count"] == 0


def test_playback_probe_rejects_internal_completion_without_ended_event() -> None:
    from scripts.windows_acceptance.playback import (
        PlaybackEvidenceError,
        validate_playback_evidence,
    )

    with pytest.raises(PlaybackEvidenceError, match="playback_not_ended"):
        validate_playback_evidence(
            {"events": [{"event": "play", "current_time": 0}], "console_errors": []}
        )


def test_render_probe_requires_h264_aac_and_positive_duration() -> None:
    from scripts.windows_acceptance.render import validate_ffprobe_payload

    metrics = validate_ffprobe_payload(
        {
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
                {"codec_type": "audio", "codec_name": "aac"},
            ],
            "format": {"duration": "12.5"},
        }
    )

    assert metrics["duration_seconds"] == 12.5


def test_render_probe_rejects_non_release_codec() -> None:
    from scripts.windows_acceptance.render import RenderEvidenceError, validate_ffprobe_payload

    with pytest.raises(RenderEvidenceError, match="video_codec_invalid"):
        validate_ffprobe_payload(
            {
                "streams": [
                    {"codec_type": "video", "codec_name": "vp9"},
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
                "format": {"duration": "1"},
            }
        )
