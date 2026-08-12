from __future__ import annotations

from pathlib import Path

import pytest
import workbench.performance.s50_acceptance as s50_acceptance
from workbench.performance.s50_acceptance import (
    _candidate_run_root,
    _temporary_file_count,
    _validate_package,
    _write_wav,
    sha256_file,
)
from workbench.video.package_service import VideoExportResult, build_package_manifest


def test_package_validation_checks_mp4_srt_and_manifest_hashes(tmp_path: Path) -> None:
    mp4 = tmp_path / "08_output" / "final.mp4"
    package = tmp_path / "08_output" / "package"
    mp4.parent.mkdir(parents=True)
    package.mkdir()
    mp4.write_bytes(b"final-media")
    packaged_mp4 = package / "final.mp4"
    packaged_srt = package / "subtitles.srt"
    packaged_mp4.write_bytes(mp4.read_bytes())
    packaged_srt.write_text("1\n00:00:00,000 --> 00:00:00,300\nS50\n", encoding="utf-8")
    manifest = build_package_manifest(package, [packaged_mp4, packaged_srt])
    (package / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")

    result = VideoExportResult(
        mp4_relative_path="08_output/final.mp4",
        package_relative_path="08_output/package",
        duration_ms=300,
        video_codec="h264",
        audio_codec="aac",
        artifact_count=3,
        cached_pages=10,
    )
    checked = _validate_package(tmp_path, result)

    assert checked["final_mp4_sha256"] == sha256_file(mp4)
    assert checked["package_manifest_artifact_count"] == 2


def test_temporary_file_count_ignores_published_render_history(tmp_path: Path) -> None:
    published = tmp_path / "08_output" / ".render-jobs" / "completed" / "page.mp4"
    temporary = tmp_path / "08_output" / ".final.mp4.example.tmp"
    published.parent.mkdir(parents=True)
    published.write_bytes(b"published history")
    temporary.write_bytes(b"unfinished publication")

    assert _temporary_file_count(tmp_path) == 1


def test_s50_creates_its_owned_workspace_before_creating_app(
    tmp_path: Path, monkeypatch
) -> None:
    observed: list[Path] = []

    def app_factory(workspace: Path, *, video_renderer: object) -> object:
        del video_renderer
        observed.append(workspace)
        raise RuntimeError("stop after workspace initialization")

    monkeypatch.setattr(s50_acceptance, "create_app", app_factory)
    with pytest.raises(RuntimeError, match="workspace initialization"):
        s50_acceptance.execute_s50_acceptance(
            tmp_path / "run",
            ffmpeg="ffmpeg",
            ffprobe="ffprobe",
        )

    assert observed == [tmp_path / "run" / "workspace"]
    assert observed[0].is_dir()


def test_candidate_run_root_is_short_and_candidate_hash_bound(tmp_path: Path) -> None:
    manifest_hash = "a" * 64
    run_root = _candidate_run_root(
        tmp_path / "test-results" / "performance-s50",
        manifest_hash,
        "s50-20260813T010203Z-12345678",
    )
    manifest_temp = (
        run_root
        / "workspace"
        / "s50_20260813_0102"
        / (".project.json." + "b" * 32 + ".tmp")
    )

    assert "candidate-aaaaaaaaaaaa" in run_root.parts
    assert len(str(manifest_temp)) < 260


def test_s50_page_audio_fixture_is_unique_per_page(tmp_path: Path) -> None:
    first = tmp_path / "page-0001.wav"
    second = tmp_path / "page-0002.wav"

    _write_wav(first, 300, page_order=1)
    _write_wav(second, 300, page_order=2)

    assert sha256_file(first) != sha256_file(second)
