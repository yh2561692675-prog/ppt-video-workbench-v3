from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from workbench.quality.engine import QualityProcessResult, QualityService
from workbench.quality.models import (
    NormalizedRect,
    PageSpan,
    QualityPolicy,
    QualityResult,
    QualityTarget,
    SubtitlePlacement,
    SubtitleSpan,
)


def _runner(command, _cwd: Path) -> QualityProcessResult:
    if command[0] == "ffprobe":
        return QualityProcessResult(
            returncode=0,
            stdout=json.dumps(
                {
                    "streams": [
                        {
                            "codec_type": "video",
                            "codec_name": "h264",
                            "width": 1920,
                            "height": 1080,
                            "r_frame_rate": "30/1",
                        },
                        {"codec_type": "audio", "codec_name": "aac"},
                    ],
                    "format": {"duration": "2.000"},
                }
            ),
        )
    if any("ebur128" in token for token in command):
        return QualityProcessResult(returncode=0, stderr="I: -20.0 LUFS\nPeak: -1.0 dBFS")
    return QualityProcessResult(returncode=0, stderr="")


def test_quality_service_passes_valid_media_and_writes_report(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"valid-media")
    page_id = uuid4()
    report_path = tmp_path / "quality-report.json"
    target = QualityTarget(
        video_path=video,
        expected_duration_ms=2000,
        pages=[PageSpan(page_id=page_id, start_ms=0, end_ms=2000)],
        subtitles=[
            SubtitleSpan(cue_id=uuid4(), page_id=page_id, start_ms=100, end_ms=500, text_length=8)
        ],
    )

    report = QualityService(runner=_runner).analyze(
        project_id=uuid4(),
        render_job_id=uuid4(),
        target=target,
        report_path=report_path,
    )

    assert report.result is QualityResult.PASS
    assert report_path.is_file()
    assert json.loads(report_path.read_text(encoding="utf-8"))["result"] == "pass"


def test_quality_fingerprint_includes_policy_and_analyzer_version(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"valid-media")
    target = QualityTarget(video_path=video, expected_duration_ms=2_000)
    project_id, render_job_id = uuid4(), uuid4()
    standard = QualityService(runner=_runner).analyze(
        project_id=project_id,
        render_job_id=render_job_id,
        target=target,
        policy=QualityPolicy.preset("standard"),
    )
    strict = QualityService(runner=_runner).analyze(
        project_id=project_id,
        render_job_id=render_job_id,
        target=target,
        policy=QualityPolicy.preset("strict"),
    )
    newer = QualityService(runner=_runner, analyzer_version="quality-engine-v2").analyze(
        project_id=project_id,
        render_job_id=render_job_id,
        target=target,
        policy=QualityPolicy.preset("standard"),
    )

    assert standard.input_fingerprint != strict.input_fingerprint
    assert standard.input_fingerprint != newer.input_fingerprint


def test_quality_service_blocks_missing_audio_and_duration_mismatch(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"valid-media")

    def runner(command, cwd):
        if command[0] == "ffprobe":
            return QualityProcessResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "streams": [
                            {
                                "codec_type": "video",
                                "codec_name": "h264",
                                "width": 1920,
                                "height": 1080,
                                "r_frame_rate": "30/1",
                            }
                        ],
                        "format": {"duration": "1.000"},
                    }
                ),
            )
        return QualityProcessResult(returncode=0)

    report = QualityService(runner=runner).analyze(
        project_id=uuid4(),
        render_job_id=uuid4(),
        target=QualityTarget(video_path=video, expected_duration_ms=2000),
    )

    assert report.result is QualityResult.BLOCKED
    assert {issue.code for issue in report.issues} >= {"audio_stream_missing", "duration_mismatch"}


def test_quality_service_parses_black_freeze_and_silence_intervals(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"valid-media")
    calls: list[list[str]] = []

    def runner(command, cwd):
        calls.append(list(command))
        if command[0] == "ffprobe":
            return QualityProcessResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "streams": [
                            {
                                "codec_type": "video",
                                "codec_name": "h264",
                                "width": 1920,
                                "height": 1080,
                                "r_frame_rate": "30/1",
                            },
                            {"codec_type": "audio", "codec_name": "aac"},
                        ],
                        "format": {"duration": "5.000"},
                    }
                ),
            )
        if any("blackdetect" in token for token in command):
            return QualityProcessResult(returncode=0, stderr="black_start:1 black_end:2")
        if any("freezedetect" in token for token in command):
            return QualityProcessResult(returncode=0, stderr="freeze_start:2 freeze_end:3")
        return QualityProcessResult(returncode=0, stderr="silence_start:3 silence_end:4.2")

    report = QualityService(runner=runner).analyze(
        project_id=uuid4(),
        render_job_id=uuid4(),
        target=QualityTarget(video_path=video, expected_duration_ms=5000),
        policy=QualityPolicy(black_frame_min_ms=500, freeze_min_ms=500, silence_min_ms=1000),
    )

    assert {issue.code for issue in report.issues} >= {
        "black_frame",
        "video_freeze",
        "audio_silence",
    }
    assert len([call for call in calls if call[0] == "ffmpeg"]) == 7


def test_quality_service_adds_scene_samples_and_detects_decode_errors(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"valid-media")

    def runner(command, _cwd: Path) -> QualityProcessResult:
        if command[0] == "ffprobe":
            return QualityProcessResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "streams": [
                            {
                                "codec_type": "video",
                                "codec_name": "h264",
                                "width": 1920,
                                "height": 1080,
                                "r_frame_rate": "30/1",
                            },
                            {"codec_type": "audio", "codec_name": "aac"},
                        ],
                        "format": {"duration": "2.000"},
                    }
                ),
            )
        if any("showinfo" in token for token in command):
            return QualityProcessResult(returncode=0, stderr="pts_time:0.750 pts_time:1.500")
        if command[-3:] == ["-f", "null", "-"]:
            return QualityProcessResult(returncode=0, stderr="Error while decoding frame")
        return QualityProcessResult(returncode=0)

    report = QualityService(runner=runner).analyze(
        project_id=uuid4(),
        render_job_id=uuid4(),
        target=QualityTarget(video_path=video, expected_duration_ms=2_000),
    )

    assert report.result is QualityResult.BLOCKED
    assert 750 in report.sampled_frames
    assert 1_500 in report.sampled_frames
    assert any(
        metric.name == "scene_change_count" and metric.value == 2 for metric in report.metrics
    )
    assert any(issue.code == "decode_error" for issue in report.issues)


def test_quality_service_degrades_scene_analysis_to_warning(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"valid-media")

    def runner(command, _cwd: Path) -> QualityProcessResult:
        if command[0] == "ffprobe":
            return QualityProcessResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "streams": [
                            {
                                "codec_type": "video",
                                "codec_name": "h264",
                                "width": 1920,
                                "height": 1080,
                                "r_frame_rate": "30/1",
                            },
                            {"codec_type": "audio", "codec_name": "aac"},
                        ],
                        "format": {"duration": "2.000"},
                    }
                ),
            )
        if any("showinfo" in token for token in command):
            return QualityProcessResult(returncode=1, stderr="filter unavailable")
        return QualityProcessResult(returncode=0)

    report = QualityService(runner=runner).analyze(
        project_id=uuid4(),
        render_job_id=uuid4(),
        target=QualityTarget(video_path=video, expected_duration_ms=2_000),
    )

    assert report.result is QualityResult.PASS_WITH_WARNINGS
    assert any(issue.code == "scene_analysis_failed" for issue in report.issues)


def test_quality_service_reports_non_consecutive_duplicate_visual_candidate(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"valid-media")

    def runner(command, _cwd: Path) -> QualityProcessResult:
        if command[0] == "ffprobe":
            return QualityProcessResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "streams": [
                            {
                                "codec_type": "video",
                                "codec_name": "h264",
                                "width": 1920,
                                "height": 1080,
                                "r_frame_rate": "30/1",
                            },
                            {"codec_type": "audio", "codec_name": "aac"},
                        ],
                        "format": {"duration": "3.000"},
                    }
                ),
            )
        if any("fps=1" in token for token in command):
            return QualityProcessResult(
                returncode=0,
                stderr=(
                    "pts_time:0.000 checksum:AAAA\n"
                    "pts_time:1.000 checksum:BBBB\n"
                    "pts_time:2.000 checksum:AAAA\n"
                ),
            )
        return QualityProcessResult(returncode=0)

    report = QualityService(runner=runner).analyze(
        project_id=uuid4(),
        render_job_id=uuid4(),
        target=QualityTarget(video_path=video, expected_duration_ms=3_000),
    )

    assert report.result is QualityResult.PASS_WITH_WARNINGS
    assert any(issue.code == "duplicate_visual_candidate" for issue in report.issues)
    assert any(
        metric.name == "duplicate_candidate_count" and metric.value == 1
        for metric in report.metrics
    )


def test_quality_service_reports_loudness_and_true_peak_violations(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"valid-media")

    def runner(command, _cwd: Path) -> QualityProcessResult:
        if command[0] == "ffprobe":
            return QualityProcessResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "streams": [
                            {
                                "codec_type": "video",
                                "codec_name": "h264",
                                "width": 1920,
                                "height": 1080,
                                "r_frame_rate": "30/1",
                            },
                            {"codec_type": "audio", "codec_name": "aac", "channels": 2},
                        ],
                        "format": {"duration": "2.000"},
                    }
                ),
            )
        if any("ebur128" in token for token in command):
            return QualityProcessResult(returncode=0, stderr="I: -35.0 LUFS\nPeak: 0.5 dBFS")
        return QualityProcessResult(returncode=0)

    report = QualityService(runner=runner).analyze(
        project_id=uuid4(),
        render_job_id=uuid4(),
        target=QualityTarget(video_path=video, expected_duration_ms=2_000),
    )

    assert report.result is QualityResult.BLOCKED
    assert {issue.code for issue in report.issues} >= {
        "audio_loudness_low",
        "audio_clipping",
    }
    assert any(metric.name == "integrated_loudness_lufs" for metric in report.metrics)
    assert any(metric.name == "true_peak_db" for metric in report.metrics)


def test_quality_service_flags_silence_inside_dialogue_and_truncated_audio(
    tmp_path: Path,
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"valid-media")
    page_id = uuid4()

    def runner(command, _cwd: Path) -> QualityProcessResult:
        if command[0] == "ffprobe":
            return QualityProcessResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "streams": [
                            {
                                "codec_type": "video",
                                "codec_name": "h264",
                                "width": 1920,
                                "height": 1080,
                                "r_frame_rate": "30/1",
                            },
                            {
                                "codec_type": "audio",
                                "codec_name": "aac",
                                "channels": 1,
                                "duration": "1.000",
                            },
                        ],
                        "format": {"duration": "2.000"},
                    }
                ),
            )
        if any("ebur128" in token for token in command):
            return QualityProcessResult(returncode=0, stderr="I: -20.0 LUFS\nPeak: -1.0 dBFS")
        if any("silencedetect" in token for token in command):
            return QualityProcessResult(returncode=0, stderr="silence_start:0 silence_end:1")
        return QualityProcessResult(returncode=0)

    report = QualityService(runner=runner).analyze(
        project_id=uuid4(),
        render_job_id=uuid4(),
        target=QualityTarget(
            video_path=video,
            expected_duration_ms=2_000,
            expected_audio_channels=2,
            subtitles=[
                SubtitleSpan(
                    cue_id=uuid4(),
                    page_id=page_id,
                    start_ms=0,
                    end_ms=1_000,
                    text_length=10,
                )
            ],
        ),
    )

    assert report.result is QualityResult.BLOCKED
    assert {issue.code for issue in report.issues} >= {
        "audio_channels_mismatch",
        "audio_tail_truncated",
        "audio_silence",
        "audio_missing_during_dialogue",
    }


def test_quality_service_blocks_when_signal_analyzers_fail(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"valid-media")

    def failing_runner(command, _cwd: Path) -> QualityProcessResult:
        if command[0] == "ffprobe":
            return QualityProcessResult(
                returncode=0,
                stdout=json.dumps(
                    {
                        "streams": [
                            {
                                "codec_type": "video",
                                "codec_name": "h264",
                                "width": 1920,
                                "height": 1080,
                                "r_frame_rate": "30/1",
                            },
                            {"codec_type": "audio", "codec_name": "aac"},
                        ],
                        "format": {"duration": "2.000"},
                    }
                ),
            )
        return QualityProcessResult(returncode=1, stderr="absolute/private/path")

    report = QualityService(runner=failing_runner).analyze(
        project_id=uuid4(),
        render_job_id=uuid4(),
        target=QualityTarget(video_path=video, expected_duration_ms=2_000),
    )

    assert report.result is QualityResult.BLOCKED
    assert {issue.code for issue in report.issues} >= {
        "video_signal_analysis_failed",
        "video_freeze_analysis_failed",
        "audio_signal_analysis_failed",
    }
    assert all("absolute/private/path" not in issue.message for issue in report.issues)


def test_quality_policy_can_promote_subtitle_density_to_blocking(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"valid-media")
    page_id = uuid4()
    report = QualityService(runner=_runner).analyze(
        project_id=uuid4(),
        render_job_id=uuid4(),
        target=QualityTarget(
            video_path=video,
            expected_duration_ms=2_000,
            pages=[PageSpan(page_id=page_id, start_ms=0, end_ms=2_000)],
            subtitles=[
                SubtitleSpan(
                    cue_id=uuid4(),
                    page_id=page_id,
                    start_ms=0,
                    end_ms=500,
                    text_length=100,
                )
            ],
        ),
        policy=QualityPolicy(max_subtitle_text_length=80, p2_blocks=True),
    )

    assert report.result is QualityResult.BLOCKED
    assert any(issue.code == "subtitle_density_high" for issue in report.issues)


def test_quality_service_reports_overlapping_page_timeline_without_invalid_range(
    tmp_path: Path,
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"valid-media")
    first, second = uuid4(), uuid4()

    report = QualityService(runner=_runner).analyze(
        project_id=uuid4(),
        render_job_id=uuid4(),
        target=QualityTarget(
            video_path=video,
            expected_duration_ms=2_000,
            pages=[
                PageSpan(page_id=first, start_ms=0, end_ms=1_200),
                PageSpan(page_id=second, start_ms=1_000, end_ms=2_000),
            ],
        ),
    )

    issue = next(item for item in report.issues if item.code == "page_timeline_gap_or_overlap")
    assert issue.start_ms is not None and issue.end_ms is not None
    assert issue.end_ms > issue.start_ms


def test_quality_service_flags_partial_subtitle_placement_when_layout_is_supplied(
    tmp_path: Path,
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"valid-media")
    first, second = uuid4(), uuid4()
    report = QualityService(runner=_runner).analyze(
        project_id=uuid4(),
        render_job_id=uuid4(),
        target=QualityTarget(
            video_path=video,
            expected_duration_ms=2_000,
            pages=[
                PageSpan(page_id=first, start_ms=0, end_ms=1_000),
                PageSpan(page_id=second, start_ms=1_000, end_ms=2_000),
            ],
            subtitles=[
                SubtitleSpan(
                    cue_id=uuid4(), page_id=second, start_ms=1_100, end_ms=1_500, text_length=4
                )
            ],
            placements=[
                SubtitlePlacement(
                    page_id=first,
                    rect=NormalizedRect(x=0.1, y=0.8, width=0.8, height=0.1),
                )
            ],
        ),
    )

    assert any(item.code == "subtitle_placement_missing" for item in report.issues)


def test_quality_service_flags_duplicate_page_ids_and_subtitle_layout_conflicts(
    tmp_path: Path,
) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"valid-media")
    page_id = uuid4()
    report = QualityService(runner=_runner).analyze(
        project_id=uuid4(),
        render_job_id=uuid4(),
        target=QualityTarget(
            video_path=video,
            expected_duration_ms=2_000,
            pages=[
                PageSpan(page_id=page_id, start_ms=0, end_ms=1_000),
                PageSpan(page_id=page_id, start_ms=1_000, end_ms=2_000),
            ],
            subtitles=[
                SubtitleSpan(
                    cue_id=uuid4(), page_id=page_id, start_ms=0, end_ms=1_000, text_length=4
                ),
                SubtitleSpan(
                    cue_id=uuid4(), page_id=page_id, start_ms=500, end_ms=1_200, text_length=0
                ),
            ],
            placements=[
                SubtitlePlacement(
                    page_id=page_id,
                    rect=NormalizedRect(x=0.1, y=0.8, width=0.5, height=0.1),
                ),
                SubtitlePlacement(
                    page_id=page_id,
                    rect=NormalizedRect(x=0.4, y=0.85, width=0.5, height=0.1),
                ),
            ],
        ),
    )

    assert {issue.code for issue in report.issues} >= {
        "page_duplicate_id",
        "subtitle_cue_overlap",
        "subtitle_empty",
        "subtitle_placement_overlap",
    }


def test_quality_service_flags_page_level_audio_visual_sync_drift(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    video.write_bytes(b"valid-media")
    first, second, unknown = uuid4(), uuid4(), uuid4()
    report = QualityService(runner=_runner).analyze(
        project_id=uuid4(),
        render_job_id=uuid4(),
        target=QualityTarget(
            video_path=video,
            expected_duration_ms=2_000,
            pages=[
                PageSpan(page_id=first, start_ms=0, end_ms=1_000),
                PageSpan(page_id=second, start_ms=1_000, end_ms=2_000),
            ],
            audio_pages=[
                PageSpan(page_id=first, start_ms=600, end_ms=1_600),
                PageSpan(page_id=unknown, start_ms=1_600, end_ms=2_000),
            ],
        ),
    )

    assert {issue.code for issue in report.issues} >= {
        "audio_visual_sync_drift",
        "audio_page_missing",
        "audio_page_unknown",
    }
