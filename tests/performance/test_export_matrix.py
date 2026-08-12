from __future__ import annotations

import pytest
from workbench.performance.export_matrix import (
    EXECUTABLE_OUTPUT_MATRIX,
    _candidate_run_root,
    _profile_props,
)
from workbench.video.models import ProjectVideoProps, VideoPageProps


def _props() -> ProjectVideoProps:
    from uuid import uuid4

    return ProjectVideoProps(
        project_id=uuid4(),
        duration_ms=1_000,
        template_version="matrix-test-v1",
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


def test_matrix_covers_all_required_aspects_resolutions_and_fps() -> None:
    matrix = {(case.width, case.height, case.fps) for case in EXECUTABLE_OUTPUT_MATRIX}
    assert {(1280, 720), (1920, 1080), (1080, 1920), (1080, 1080)} <= {
        (width, height) for width, height, _ in matrix
    }
    assert {24, 25, 30, 60} <= {fps for _, _, fps in matrix}


def test_matrix_profile_changes_only_delivery_geometry_and_rate() -> None:
    base = _props()
    profile = EXECUTABLE_OUTPUT_MATRIX[-1]
    resolved = _profile_props(base, profile)
    assert (resolved.width, resolved.height, resolved.fps) == (1080, 1080, 30)
    assert resolved.model_dump(exclude={"width", "height", "fps"}) == base.model_dump(
        exclude={"width", "height", "fps"}
    )


def test_matrix_run_root_must_be_new(tmp_path) -> None:
    from workbench.performance.export_matrix import execute_output_matrix

    run_root = tmp_path / "run"
    run_root.mkdir()
    with pytest.raises(FileExistsError):
        execute_output_matrix(run_root, ffmpeg="ffmpeg", ffprobe="ffprobe")


def test_matrix_fixture_creates_its_media_directories(tmp_path) -> None:
    from workbench.performance.export_matrix import _create_fixture
    from workbench.services.project_service import ProjectService

    projects = ProjectService(tmp_path)
    fixture = _create_fixture(projects)
    assert (fixture.project_root / "02_pages" / "page-0001.png").is_file()
    assert (fixture.project_root / "05_audio" / "page-0001.wav").is_file()


def test_matrix_runtime_root_uses_a_short_candidate_manifest_prefix(tmp_path) -> None:
    manifest_sha256 = "a" * 64
    root = _candidate_run_root(tmp_path, manifest_sha256, "r-matrix-20260813T030117Z-4913262d")
    assert root == tmp_path / "c-aaaaaaaaaaaa" / "r-matrix-20260813T030117Z-4913262d"
