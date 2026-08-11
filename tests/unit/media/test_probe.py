from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest
from workbench.media.probe import MediaProbeError, probe_media


def _runner(
    payload: Mapping[str, object],
) -> Callable[[Sequence[str]], subprocess.CompletedProcess[str]]:
    def run(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
        if list(command)[1:] == ["-version"]:
            return subprocess.CompletedProcess(command, 0, "ffprobe version 7.1", "")
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    return run


def test_probe_parses_video_audio_and_subtitle_metadata(tmp_path: Path) -> None:
    source = tmp_path / "媒体 文件.mp4"
    source.write_bytes(b"fixture")
    payload = {
        "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "2.5"},
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "duration": "2.5",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30000/1001",
                "pix_fmt": "yuv420p",
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
            },
            {
                "index": 2,
                "codec_type": "subtitle",
                "codec_name": "webvtt",
                "tags": {"language": "zh"},
            },
        ],
    }

    result = probe_media(source, runner=_runner(payload))

    assert result.duration_us == 2_500_000
    assert result.streams[0].fps_num == 30_000
    assert result.streams[0].fps_den == 1_001
    assert result.streams[1].sample_rate == 48_000
    assert result.streams[2].language == "zh"
    assert result.tool_version == "ffprobe version 7.1"


@pytest.mark.parametrize(
    "payload",
    [
        {"format": {"format_name": "mp4", "duration": "0"}, "streams": []},
        {"format": {"format_name": "mp4"}, "streams": [{"index": 0}]},
        {"format": {"format_name": "mp4", "duration": "N/A"}, "streams": [{"index": 0}]},
    ],
)
def test_probe_rejects_incomplete_or_invalid_results(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    source = tmp_path / "fixture.mp4"
    source.write_bytes(b"fixture")

    with pytest.raises(MediaProbeError, match="invalid ffprobe JSON"):
        probe_media(source, runner=_runner(payload))


def test_probe_reports_missing_input(tmp_path: Path) -> None:
    with pytest.raises(MediaProbeError, match="does not exist"):
        probe_media(tmp_path / "missing.mp4", runner=_runner({}))


@pytest.mark.parametrize(
    ("runner", "code"),
    [
        (
            lambda _: (_ for _ in ()).throw(OSError("ffprobe missing")),
            "ffprobe_unavailable",
        ),
        (
            lambda command: subprocess.CompletedProcess(command, 1, "", "bad media"),
            "ffprobe_failed",
        ),
        (
            lambda command: subprocess.CompletedProcess(command, 0, "{broken", ""),
            "ffprobe_invalid_output",
        ),
    ],
)
def test_probe_reports_structured_process_failures(
    tmp_path: Path,
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str]],
    code: str,
) -> None:
    source = tmp_path / "fixture.mp4"
    source.write_bytes(b"fixture")

    with pytest.raises(MediaProbeError) as error:
        probe_media(source, runner=runner)
    assert error.value.code == code
