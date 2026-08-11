from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from workbench.assets.derivative_models import DerivativeOperation, DerivativeRequestV1
from workbench.assets.object_store import ContentAddressedObjectStore
from workbench.assets.video_executor import VideoDerivativeError, VideoDerivativeExecutor
from workbench.media.probe import MediaProbeResult, MediaStreamProbe
from workbench.video.process_runner import ProcessControl, ProcessResult


class FixtureRunner:
    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(self, command: list[str], cwd: Path, control: ProcessControl) -> ProcessResult:
        self.commands.append(command)
        Path(command[-1]).write_bytes(b"derived-media")
        return ProcessResult(returncode=0, stdout="", stderr="")


class FailingRunner:
    def run(self, command: list[str], cwd: Path, control: ProcessControl) -> ProcessResult:
        return ProcessResult(returncode=1, stdout="", stderr="ffmpeg rejected input")


def _probe(_: Path) -> MediaProbeResult:
    return MediaProbeResult(
        container="mp4",
        duration_us=1_000_000,
        streams=[MediaStreamProbe(index=0, kind="video", codec="h264")],
        tool_version="ffprobe fixture",
    )


def _request(operation: DerivativeOperation, parameters: dict[str, object]) -> DerivativeRequestV1:
    return DerivativeRequestV1(
        parent_asset_id=uuid4(),
        parent_revision=1,
        parent_content_hash="a" * 64,
        operation=operation,
        parameters=parameters,
        output_slot="proxy",
        tool_fingerprint="b" * 64,
    )


def test_video_proxy_uses_argument_array_and_publishes_verified_output(tmp_path: Path) -> None:
    source = tmp_path / "source video.mp4"
    source.write_bytes(b"source")
    runner = FixtureRunner()
    store = ContentAddressedObjectStore(tmp_path / "store")
    executor = VideoDerivativeExecutor(
        store, tmp_path / "work", process_runner=runner, media_probe=_probe
    )

    stored = executor.execute(
        _request(DerivativeOperation.PROXY, {"width": 720, "crf": 25}), source
    )

    assert store.open_verified(stored).read_bytes() == b"derived-media"
    assert runner.commands[0][0] == "ffmpeg"
    assert runner.commands[0][runner.commands[0].index("-i") + 1] == str(source)
    assert "shell" not in runner.commands[0]


def test_video_executor_rejects_unknown_and_invalid_parameters(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    executor = VideoDerivativeExecutor(
        ContentAddressedObjectStore(tmp_path / "store"),
        tmp_path / "work",
        process_runner=FixtureRunner(),
        media_probe=_probe,
    )

    with pytest.raises(VideoDerivativeError, match="unsupported video parameters"):
        executor.execute(_request(DerivativeOperation.PROXY, {"command": "bad"}), source)
    with pytest.raises(VideoDerivativeError, match="audio_bitrate"):
        executor.execute(
            _request(DerivativeOperation.TRANSCODE, {"audio_bitrate": "$(bad)"}), source
        )


def test_video_executor_rejects_ffmpeg_failures(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    source.write_bytes(b"source")
    executor = VideoDerivativeExecutor(
        ContentAddressedObjectStore(tmp_path / "store"),
        tmp_path / "work",
        process_runner=FailingRunner(),
        media_probe=_probe,
    )

    with pytest.raises(VideoDerivativeError, match="rejected input"):
        executor.execute(_request(DerivativeOperation.PROXY, {}), source)
