from __future__ import annotations

import pytest
from workbench.exports.presets import ExportPresetService
from workbench.exports.video_profiles import ExportProfileBlocked, ExportProfileCapabilities
from workbench.video.models import ProjectVideoProps, VideoPageProps


def _props() -> ProjectVideoProps:
    from uuid import uuid4

    return ProjectVideoProps(
        project_id=uuid4(),
        duration_ms=1_000,
        template_version="profile-test-v1",
        pages=[
            VideoPageProps(
                page_id=uuid4(),
                page_order=1,
                image_path="page.png",
                audio_path="audio.wav",
                start_ms=0,
                end_ms=1_000,
            )
        ],
    )


def test_qualified_presets_resolve_to_720p_1080p_and_all_supported_fps(tmp_path) -> None:
    service = ExportPresetService(tmp_path, project_dir_resolver=lambda _: "project")
    cases = {
        "master-720p-24": (1280, 720, 24),
        "master-720p-25": (1280, 720, 25),
        "master-1080p-30": (1920, 1080, 30),
        "youtube-1080p-60": (1920, 1080, 60),
        "bilibili-vertical-1080p-30": (1080, 1920, 30),
        "douyin-square-1080p-30": (1080, 1080, 30),
    }
    for preset_id, expected in cases.items():
        props = service.resolve_video_props(_props(), preset_id)
        assert (props.width, props.height, props.fps) == expected


def test_4k_requires_feature_and_launcher_hardware_capability(tmp_path) -> None:
    service = ExportPresetService(tmp_path, project_dir_resolver=lambda _: "project")
    with pytest.raises(ExportProfileBlocked, match="4K requires"):
        service.resolve_video_props(_props(), "master-4k-30")

    resolved = service.resolve_video_props(
        _props(),
        "master-4k-30",
        capabilities=ExportProfileCapabilities(True, True),
    )
    assert (resolved.width, resolved.height, resolved.fps) == (3840, 2160, 30)


def test_gif_is_not_queued_as_a_video_export_before_renderer_support_exists(tmp_path) -> None:
    service = ExportPresetService(tmp_path, project_dir_resolver=lambda _: "project")
    with pytest.raises(ExportProfileBlocked, match="MP4"):
        service.resolve_video_props(_props(), "gif-720p-24")
