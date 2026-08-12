from pathlib import Path
from uuid import uuid4

import pytest
from workbench.video.errors import RenderInputStale
from workbench.video.package_service import (
    PackageError,
    VideoExportError,
    VideoExportService,
    _probe_fps,
    build_final_concat_command,
    build_package_manifest,
    build_page_mux_command,
    validate_media_probe,
)
from workbench.video.process_runner import ProcessCancelled, ProcessExecutionError


def test_presenter_page_mux_seeks_the_single_master_audio_track(tmp_path: Path) -> None:
    command = build_page_mux_command(
        "ffmpeg",
        tmp_path / "page.mp4",
        tmp_path / "presenter.mp4",
        tmp_path / "segment.mp4",
        start_ms=12_500,
        end_ms=15_000,
        seek_master_audio=True,
    )

    assert command[command.index("-ss") + 1] == "12.500"
    assert command[command.index("-t") + 1] == "2.500"
    assert command.count(str(tmp_path / "presenter.mp4")) == 1


def test_ai_page_mux_does_not_seek_page_audio(tmp_path: Path) -> None:
    command = build_page_mux_command(
        "ffmpeg",
        tmp_path / "page.mp4",
        tmp_path / "page.wav",
        tmp_path / "segment.mp4",
        start_ms=12_500,
        end_ms=15_000,
        seek_master_audio=False,
    )

    assert "-ss" not in command


def test_final_concat_reencodes_to_the_frozen_constant_frame_rate(tmp_path: Path) -> None:
    command = build_final_concat_command(
        "ffmpeg",
        tmp_path / "concat.txt",
        tmp_path / "final.mp4",
        duration_ms=2_000,
        fps=24,
    )

    assert "copy" not in command
    assert command[command.index("-vf") + 1] == "fps=24,format=yuv420p"
    assert command[command.index("-r") + 1] == "24"
    assert command[command.index("-c:v") + 1] == "libx264"
    assert command[command.index("-c:a") + 1] == "aac"


def test_package_manifest_contains_sha256_and_size_for_required_artifacts(tmp_path: Path) -> None:
    video = tmp_path / "最终视频.mp4"
    subtitles = tmp_path / "字幕.srt"
    video.write_bytes(b"video-bytes")
    subtitles.write_text("1\n00:00:00,000 --> 00:00:01,000\n字幕\n", encoding="utf-8")

    manifest = build_package_manifest(tmp_path, [video, subtitles])

    assert [item.relative_path for item in manifest.artifacts] == ["最终视频.mp4", "字幕.srt"]
    assert manifest.artifacts[0].size == len(b"video-bytes")
    assert len(manifest.artifacts[0].sha256) == 64
    assert manifest.artifacts[1].sha256 != manifest.artifacts[0].sha256


def test_package_manifest_rejects_missing_or_outside_artifacts(tmp_path: Path) -> None:
    with pytest.raises(PackageError, match="缺少制作包文件"):
        build_package_manifest(tmp_path, [tmp_path / "missing.mp4"])

    outside = tmp_path.parent / "outside.bin"
    outside.write_bytes(b"outside")
    with pytest.raises(PackageError, match="超出制作包目录"):
        build_package_manifest(tmp_path, [outside])


def test_media_probe_rejects_duration_outside_declared_tolerance() -> None:
    probe = {
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "video_codec": "h264",
        "audio_codec": "aac",
        "duration_ms": 1_250,
    }

    with pytest.raises(VideoExportError, match="时长"):
        validate_media_probe(probe, expected_duration_ms=1_000, tolerance_ms=100)


def test_media_probe_accepts_vertical_props_dimensions() -> None:
    validate_media_probe(
        {
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "video_codec": "h264",
            "audio_codec": "aac",
            "duration_ms": 1_000,
        },
        expected_duration_ms=1_000,
        tolerance_ms=100,
        expected_width=1080,
        expected_height=1920,
        expected_fps=30,
    )


def test_probe_fps_normalizes_ffprobe_rationals_and_rejects_malformed_values() -> None:
    assert _probe_fps({"avg_frame_rate": "60000/1000"}) == 60
    assert _probe_fps({"r_frame_rate": "25/1"}) == 25
    assert _probe_fps({"avg_frame_rate": "0/0"}) is None


def test_async_export_rejects_stale_input_before_rendering(tmp_path: Path) -> None:
    project_id = uuid4()

    class Props:
        def model_dump(self, mode=None):
            return {"pages": []}

    class Preview:
        def preflight(self, requested_id):
            assert requested_id == project_id
            return type(
                "Preflight",
                (),
                {"allowed": True, "props": Props(), "input_fingerprint": "current"},
            )()

    class Projects:
        workspace_root = tmp_path

        def get(self, requested_id):
            return type("Project", (), {"project_dir": "project"})()

    context = type(
        "Context",
        (),
        {"job_id": uuid4(), "input_fingerprint": "stale"},
    )()
    service = VideoExportService(Projects(), Preview())

    with pytest.raises(RenderInputStale):
        service.export(project_id, context=context)


def test_ffmpeg_probe_fallback_uses_the_cancellable_runner(tmp_path: Path) -> None:
    control = type(
        "Control",
        (),
        {"cancel_requested": True, "heartbeat": lambda self: None},
    )()

    class Runner:
        calls = 0

        def run(self, command, cwd, received_control):
            self.calls += 1
            assert received_control is control
            if self.calls == 1:
                raise ProcessExecutionError("ffprobe unavailable")
            assert "-hide_banner" in command
            raise ProcessCancelled("cancelled")

    runner = Runner()
    service = VideoExportService(object(), object(), process_runner=runner)
    media = tmp_path / "video.mp4"
    media.write_bytes(b"video")

    with pytest.raises(ProcessCancelled):
        service._probe(media, control)
    assert runner.calls == 2
