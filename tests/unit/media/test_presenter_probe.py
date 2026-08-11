import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from workbench.media.presenter_probe import PresenterMediaError, probe_presenter


def _runner(payload: dict[str, object], seen: list[list[str]]):
    def run(command: list[str]) -> CompletedProcess[str]:
        seen.append(command)
        return CompletedProcess(command, 0, stdout=json.dumps(payload), stderr="")

    return run


def test_probe_rejects_video_without_audio(tmp_path: Path) -> None:
    source = tmp_path / "中文路径" / "讲解.mp4"
    source.parent.mkdir()
    source.write_bytes(b"fixture")
    seen: list[list[str]] = []
    payload = {
        "format": {"duration": "12.5", "format_name": "mov,mp4"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 1920,
                "height": 1080,
                "avg_frame_rate": "30/1",
                "r_frame_rate": "30/1",
            }
        ],
    }

    with pytest.raises(PresenterMediaError) as captured:
        probe_presenter(source, runner=_runner(payload, seen))

    assert captured.value.code == "PRESENTER_AUDIO_MISSING"
    assert isinstance(seen[0], list)
    assert seen[0][-1] == str(source)


def test_probe_returns_stable_metadata_and_warnings(tmp_path: Path) -> None:
    source = tmp_path / "presenter.mov"
    source.write_bytes(b"presenter-video")
    payload = {
        "format": {"duration": "8.25", "format_name": "mov,mp4"},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": "h264",
                "width": 960,
                "height": 540,
                "avg_frame_rate": "30000/1001",
                "r_frame_rate": "30/1",
                "start_time": "0.0",
                "time_base": "1/30000",
            },
            {
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
            },
        ],
    }

    result = probe_presenter(source, runner=_runner(payload, []))

    assert result.duration_ms == 8_250
    assert result.width == 960
    assert result.sample_rate == 48_000
    assert result.sha256
    assert result.warnings == ["PRESENTER_LOW_RESOLUTION", "PRESENTER_VARIABLE_FPS"]
