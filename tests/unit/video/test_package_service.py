from pathlib import Path

import pytest
from workbench.video.package_service import (
    PackageError,
    VideoExportError,
    build_package_manifest,
    validate_media_probe,
)


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
            "video_codec": "h264",
            "audio_codec": "aac",
            "duration_ms": 1_000,
        },
        expected_duration_ms=1_000,
        tolerance_ms=100,
        expected_width=1080,
        expected_height=1920,
    )
