from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from workbench.quality.canonical import canonical_hash, file_hash
from workbench.quality.models import (
    MediaProbe,
    NormalizedRect,
    QualityIssue,
    QualityMetric,
    QualityPolicy,
    QualityReport,
    QualityResult,
    QualityScope,
    QualitySeverity,
    QualityTarget,
    RetryPolicy,
    SubtitlePlacement,
    SubtitleSpan,
)


class QualityProcessResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    returncode: int
    stdout: str = ""
    stderr: str = ""


ProcessRunner = Callable[[Sequence[str], Path], QualityProcessResult]
_DECODE_ERROR_RE = re.compile(
    r"\b(?:error|invalid|corrupt|truncated|could not decode)\b", re.IGNORECASE
)
_SCENE_POINT_RE = re.compile(r"pts_time:\s*(-?\d+(?:\.\d+)?)")
_FRAME_CHECKSUM_RE = re.compile(r"checksum:\s*([0-9A-Fa-f]+)")


class QualityService:
    """Run deterministic media and structure checks without changing project state."""

    def __init__(
        self,
        *,
        runner: ProcessRunner | None = None,
        analyzer_version: str = "quality-engine-v1",
    ) -> None:
        self.runner = runner or _subprocess_runner
        self.analyzer_version = analyzer_version

    def analyze(
        self,
        *,
        project_id: UUID,
        render_job_id: UUID,
        target: QualityTarget,
        policy: QualityPolicy | None = None,
        report_path: Path | None = None,
        report_relative_path: str | None = None,
        render_provenance: Mapping[str, str] | None = None,
    ) -> QualityReport:
        selected_policy = policy or QualityPolicy()
        issues: list[QualityIssue] = []
        metrics: list[QualityMetric] = []
        sampled_frames = self._sample_frames(target)

        if not target.video_path.is_file():
            issues.append(
                _issue(
                    "media_file_missing",
                    QualitySeverity.P0,
                    "成片文件不存在",
                    "重新执行渲染并确认输出目录可写",
                    RetryPolicy.REASSEMBLE,
                )
            )
            return self._finish(
                project_id,
                render_job_id,
                target,
                issues,
                metrics,
                sampled_frames,
                report_path,
                report_relative_path,
                selected_policy,
                blocks_p2=selected_policy.p2_blocks,
                render_provenance=render_provenance,
            )

        probe = self._probe(target.video_path, issues)
        metrics.extend(_probe_metrics(probe))
        issues.extend(self._check_probe(probe, target))
        if probe.has_video:
            scene_samples, scene_failed = self._scan_scene_changes(target.video_path)
            sampled_frames = sorted(set(sampled_frames).union(scene_samples))
            metrics.append(QualityMetric(name="scene_change_count", value=len(scene_samples)))
            if scene_failed:
                issues.append(
                    _issue(
                        "scene_analysis_failed",
                        QualitySeverity.P2,
                        "无法完成场景变化分析",
                        "检查 FFmpeg 运行时后重试，或保留结构抽检结果",
                        RetryPolicy.NONE,
                    )
                )
            duplicate_issues, duplicate_failed = self._scan_duplicate_frames(target.video_path)
            metrics.append(
                QualityMetric(
                    name="duplicate_candidate_count",
                    value=len(duplicate_issues),
                )
            )
            issues.extend(duplicate_issues)
            if duplicate_failed:
                issues.append(
                    _issue(
                        "duplicate_analysis_failed",
                        QualitySeverity.P2,
                        "无法完成重复片段候选分析",
                        "检查 FFmpeg 运行时后重试，或保留其他视频信号结果",
                        RetryPolicy.NONE,
                    )
                )
            issues.extend(self._scan_decode_errors(target.video_path))
        if probe.has_video:
            issues.extend(self._scan_black_frames(target.video_path, selected_policy))
            issues.extend(self._scan_freeze(target.video_path, selected_policy))
        if probe.has_audio:
            loudness_metrics, loudness_issues, loudness_failed = self._scan_loudness(
                target.video_path,
                selected_policy,
            )
            metrics.extend(loudness_metrics)
            issues.extend(loudness_issues)
            if loudness_failed:
                issues.append(
                    _issue(
                        "audio_loudness_analysis_failed",
                        QualitySeverity.P2,
                        "无法完成响度和真峰值分析",
                        "检查 FFmpeg 音频滤镜后重试，或保留其他音频结果",
                        RetryPolicy.NONE,
                    )
                )
            silence_issues = self._scan_silence(target.video_path, selected_policy)
            issues.extend(silence_issues)
            issues.extend(_dialogue_silence_issues(target.subtitles, silence_issues))
        issues.extend(self._check_structure(target))
        issues.extend(self._check_sync(target, selected_policy))
        issues.extend(self._check_subtitles(target, selected_policy))
        return self._finish(
            project_id,
            render_job_id,
            target,
            issues,
            metrics,
            sampled_frames,
            report_path,
            report_relative_path,
            selected_policy,
            blocks_p2=selected_policy.p2_blocks,
            render_provenance=render_provenance,
        )

    def _probe(self, path: Path, issues: list[QualityIssue]) -> MediaProbe:
        try:
            result = self.runner(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_streams",
                    "-show_format",
                    "-of",
                    "json",
                    str(path),
                ],
                path.parent,
            )
            if result.returncode != 0:
                raise ValueError("ffprobe returned non-zero")
            payload = json.loads(result.stdout)
            return _parse_probe(payload)
        except (OSError, ValueError, TypeError, json.JSONDecodeError, KeyError):
            issues.append(
                _issue(
                    "media_probe_failed",
                    QualitySeverity.P0,
                    "无法读取成片媒体信息",
                    "检查 FFprobe、文件完整性和编码运行时后重试",
                    RetryPolicy.REASSEMBLE,
                )
            )
            return MediaProbe()

    def _check_probe(self, probe: MediaProbe, target: QualityTarget) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        if not probe.has_video:
            issues.append(
                _issue(
                    "video_stream_missing",
                    QualitySeverity.P0,
                    "成片缺少视频流",
                    "重新合成成片",
                    RetryPolicy.REASSEMBLE,
                )
            )
        if not probe.has_audio:
            issues.append(
                _issue(
                    "audio_stream_missing",
                    QualitySeverity.P0,
                    "成片缺少音频流",
                    "检查页面音频和混音输入",
                    RetryPolicy.REASSEMBLE,
                )
            )
        if probe.width != target.expected_width or probe.height != target.expected_height:
            issues.append(
                _issue(
                    "video_dimensions_mismatch",
                    QualitySeverity.P0,
                    "成片画布尺寸不符合项目契约",
                    "检查画幅设置后重新渲染",
                    RetryPolicy.RECOMPILE,
                )
            )
        if probe.video_codec != target.expected_video_codec:
            issues.append(
                _issue(
                    "video_codec_mismatch",
                    QualitySeverity.P0,
                    "视频编码不符合项目契约",
                    "使用受支持的渲染运行时重新导出",
                    RetryPolicy.REASSEMBLE,
                )
            )
        if probe.audio_codec != target.expected_audio_codec:
            issues.append(
                _issue(
                    "audio_codec_mismatch",
                    QualitySeverity.P0,
                    "音频编码不符合项目契约",
                    "使用受支持的音频编码重新导出",
                    RetryPolicy.REASSEMBLE,
                )
            )
        if (
            target.expected_audio_channels is not None
            and probe.audio_channels != target.expected_audio_channels
        ):
            issues.append(
                _issue(
                    "audio_channels_mismatch",
                    QualitySeverity.P1,
                    "音频声道数与项目契约不一致",
                    "检查混音声道设置后重新导出",
                    RetryPolicy.REASSEMBLE,
                )
            )
        elif probe.audio_channels == 1:
            issues.append(
                _issue(
                    "audio_mono",
                    QualitySeverity.P2,
                    "成片音频为单声道",
                    "确认单声道是否符合项目要求",
                    RetryPolicy.NONE,
                )
            )
        if probe.fps is None or abs(probe.fps - target.expected_fps) > 0.01:
            issues.append(
                _issue(
                    "video_fps_mismatch",
                    QualitySeverity.P1,
                    "成片帧率与项目契约不一致",
                    "检查渲染帧率设置后重新导出",
                    RetryPolicy.REASSEMBLE,
                )
            )
        if (
            probe.duration_ms is None
            or abs(probe.duration_ms - target.expected_duration_ms) > target.duration_tolerance_ms
        ):
            issues.append(
                _issue(
                    "duration_mismatch",
                    QualitySeverity.P1,
                    "成片时长与时间线不一致",
                    "检查页面时间线和音频尾部后重新合成",
                    RetryPolicy.RECOMPILE,
                )
            )
        if (
            probe.audio_duration_ms is not None
            and target.expected_duration_ms - probe.audio_duration_ms > target.duration_tolerance_ms
        ):
            issues.append(
                _issue(
                    "audio_tail_truncated",
                    QualitySeverity.P1,
                    "音频尾部短于项目时间线",
                    "检查音频导出和尾部混音后重新合成",
                    RetryPolicy.REASSEMBLE,
                )
            )
        return issues

    def _scan_black_frames(self, path: Path, policy: QualityPolicy) -> list[QualityIssue]:
        result = self._run_filter(
            path,
            [
                "-vf",
                f"blackdetect=d={policy.black_frame_min_ms / 1000:.3f}:pic_th=0.98",
                "-c:v",
                "rawvideo",
                "-f",
                "null",
                "-",
            ],
        )
        if result.returncode != 0:
            return [_signal_analysis_failure("video_signal_analysis_failed")]
        return _parse_intervals(
            result.stderr,
            start_key="black_start",
            end_key="black_end",
            min_ms=policy.black_frame_min_ms,
            code="black_frame",
            message="检测到连续黑帧",
            action="检查页面素材、转场和编码输出",
            severity=QualitySeverity.P1,
        )

    def _scan_freeze(self, path: Path, policy: QualityPolicy) -> list[QualityIssue]:
        result = self._run_filter(
            path,
            [
                "-vf",
                f"freezedetect=n=-60dB:d={policy.freeze_min_ms / 1000:.3f}",
                "-c:v",
                "rawvideo",
                "-f",
                "null",
                "-",
            ],
        )
        if result.returncode != 0:
            return [_signal_analysis_failure("video_freeze_analysis_failed")]
        return _parse_intervals(
            result.stderr,
            start_key="freeze_start",
            end_key="freeze_end",
            min_ms=policy.freeze_min_ms,
            code="video_freeze",
            message="检测到疑似画面冻结",
            action="检查页面渲染进程和素材是否重复",
            severity=QualitySeverity.P1,
        )

    def _scan_silence(self, path: Path, policy: QualityPolicy) -> list[QualityIssue]:
        result = self._run_filter(
            path,
            [
                "-af",
                f"silencedetect=n=-50dB:d={policy.silence_min_ms / 1000:.3f}",
                "-vn",
                "-f",
                "null",
                "-",
            ],
        )
        if result.returncode != 0:
            return [_signal_analysis_failure("audio_signal_analysis_failed")]
        return _parse_intervals(
            result.stderr,
            start_key="silence_start",
            end_key="silence_end",
            min_ms=policy.silence_min_ms,
            code="audio_silence",
            message="检测到连续静音区间",
            action="确认该段是否为有意停顿，否则检查页面音频",
            severity=QualitySeverity.P2,
        )

    def _scan_loudness(
        self,
        path: Path,
        policy: QualityPolicy,
    ) -> tuple[list[QualityMetric], list[QualityIssue], bool]:
        result = self._run_filter(
            path,
            [
                "-af",
                "ebur128=framelog=verbose",
                "-vn",
                "-f",
                "null",
                "-",
            ],
        )
        if result.returncode != 0:
            return [], [], True
        integrated = _parse_loudness_value(result.stderr, r"\bI:")
        true_peak = _parse_loudness_value(result.stderr, r"\b(?:Peak|True peak):")
        if integrated is None and true_peak is None:
            return [], [], True
        metrics: list[QualityMetric] = []
        issues: list[QualityIssue] = []
        if integrated is not None:
            metrics.append(
                QualityMetric(name="integrated_loudness_lufs", value=integrated, unit="LUFS")
            )
            if integrated < policy.min_integrated_lufs:
                issues.append(
                    _issue(
                        "audio_loudness_low",
                        QualitySeverity.P2,
                        "整片响度低于策略下限",
                        "确认旁白增益和混音响度后重新导出",
                        RetryPolicy.REASSEMBLE,
                    )
                )
        if true_peak is not None:
            metrics.append(QualityMetric(name="true_peak_db", value=true_peak, unit="dBTP"))
            if true_peak > policy.max_true_peak_db:
                issues.append(
                    _issue(
                        "audio_clipping",
                        QualitySeverity.P1,
                        "音频真峰值超过削波策略上限",
                        "降低混音峰值后重新导出",
                        RetryPolicy.REASSEMBLE,
                    )
                )
        return metrics, issues, False

    def _scan_scene_changes(self, path: Path) -> tuple[list[int], bool]:
        result = self._run_filter(
            path,
            [
                "-vf",
                "select='gt(scene,0.40)',showinfo",
                "-an",
                "-c:v",
                "rawvideo",
                "-f",
                "null",
                "-",
            ],
        )
        return _parse_scene_points(result.stderr), result.returncode != 0

    def _scan_decode_errors(self, path: Path) -> list[QualityIssue]:
        result = self._run_filter(path, ["-c:v", "rawvideo", "-f", "null", "-"])
        if result.returncode == 0 and not _DECODE_ERROR_RE.search(result.stderr):
            return []
        return [
            _issue(
                "decode_error",
                QualitySeverity.P0,
                "成片存在解码错误",
                "检查源素材和编码输出后重新合成",
                RetryPolicy.REASSEMBLE,
            )
        ]

    def _scan_duplicate_frames(self, path: Path) -> tuple[list[QualityIssue], bool]:
        result = self._run_filter(
            path,
            [
                "-vf",
                "fps=1,scale=16:16:flags=neighbor,format=gray,showinfo",
                "-an",
                "-c:v",
                "rawvideo",
                "-f",
                "null",
                "-",
            ],
        )
        if result.returncode != 0:
            return [], True
        frames = _parse_frame_signatures(result.stderr)
        issues: list[QualityIssue] = []
        previous_by_signature: dict[str, tuple[int, int]] = {}
        signatures: list[str] = []
        for timestamp_ms, signature in frames:
            previous = previous_by_signature.get(signature)
            if previous is not None:
                previous_ms, previous_index = previous
                if any(item != signature for item in signatures[previous_index + 1 :]):
                    issues.append(
                        _issue(
                            "duplicate_visual_candidate",
                            QualitySeverity.P2,
                            "检测到非连续重复画面候选",
                            "确认是否为重复页面或保留的循环素材",
                            RetryPolicy.NONE,
                            start_ms=previous_ms,
                            end_ms=max(previous_ms + 1, timestamp_ms),
                        )
                    )
                    previous_by_signature.pop(signature)
            previous_by_signature[signature] = (timestamp_ms, len(signatures))
            signatures.append(signature)
        return issues, False

    def _run_filter(self, path: Path, options: list[str]) -> QualityProcessResult:
        try:
            return self.runner(["ffmpeg", "-hide_banner", "-i", str(path), *options], path.parent)
        except (OSError, ValueError):
            return QualityProcessResult(returncode=1, stderr="filter process unavailable")

    def _check_structure(self, target: QualityTarget) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        pages = sorted(target.pages, key=lambda item: item.start_ms)
        previous_end = 0
        seen_page_ids: set[UUID] = set()
        for page in pages:
            if page.page_id in seen_page_ids:
                issues.append(
                    _issue(
                        "page_duplicate_id",
                        QualitySeverity.P1,
                        "页面时间线包含重复 page ID",
                        "重新编译页面时间线并确保每页身份唯一",
                        RetryPolicy.RECOMPILE,
                        page_id=page.page_id,
                    )
                )
            seen_page_ids.add(page.page_id)
            if page.start_ms != previous_end:
                range_start = min(previous_end, page.start_ms)
                range_end = max(previous_end, page.start_ms)
                issues.append(
                    _issue(
                        "page_timeline_gap_or_overlap",
                        QualitySeverity.P1,
                        "页面时间线存在空洞或重叠",
                        "重新编译项目时间线",
                        RetryPolicy.RECOMPILE,
                        page_id=page.page_id,
                        start_ms=range_start,
                        end_ms=max(range_start + 1, range_end),
                    )
                )
            previous_end = page.end_ms
        if pages and abs(previous_end - target.expected_duration_ms) > target.duration_tolerance_ms:
            issues.append(
                _issue(
                    "page_timeline_duration_mismatch",
                    QualitySeverity.P1,
                    "页面时间线总时长与成片预期不一致",
                    "重新编译页面时间线",
                    RetryPolicy.RECOMPILE,
                )
            )
        known_pages = {page.page_id for page in pages}
        for subtitle in target.subtitles:
            if subtitle.page_id not in known_pages:
                issues.append(
                    _issue(
                        "subtitle_unknown_page",
                        QualitySeverity.P1,
                        "字幕引用了未知页面",
                        "重新生成字幕时间线",
                        RetryPolicy.RECOMPILE,
                        page_id=subtitle.page_id,
                    )
                )
        return issues

    def _check_subtitles(self, target: QualityTarget, policy: QualityPolicy) -> list[QualityIssue]:
        issues: list[QualityIssue] = []
        page_by_id = {page.page_id: page for page in target.pages}
        cues_by_page: dict[UUID, list[SubtitleSpan]] = {}
        for cue in target.subtitles:
            page = page_by_id.get(cue.page_id)
            if page is None:
                continue
            cues_by_page.setdefault(cue.page_id, []).append(cue)
            if cue.start_ms < page.start_ms or cue.end_ms > page.end_ms:
                issues.append(
                    _issue(
                        "subtitle_crosses_page_boundary",
                        QualitySeverity.P1,
                        "字幕超出所属页面时间范围",
                        "重新生成或人工调整字幕分页",
                        RetryPolicy.RECOMPILE,
                        page_id=cue.page_id,
                        start_ms=cue.start_ms,
                        end_ms=cue.end_ms,
                    )
                )
            if cue.text_length == 0:
                issues.append(
                    _issue(
                        "subtitle_empty",
                        QualitySeverity.P2,
                        "字幕 cue 没有可显示文本",
                        "删除空 cue 或重新生成字幕",
                        RetryPolicy.RECOMPILE,
                        page_id=cue.page_id,
                        start_ms=cue.start_ms,
                        end_ms=cue.end_ms,
                    )
                )
            if cue.text_length > policy.max_subtitle_text_length:
                issues.append(
                    _issue(
                        "subtitle_density_high",
                        QualitySeverity.P2,
                        "单条字幕文本过长，可能影响可读性",
                        "拆分字幕或调整字幕样式",
                        RetryPolicy.NONE,
                        page_id=cue.page_id,
                        start_ms=cue.start_ms,
                        end_ms=cue.end_ms,
                    )
                )
        for page_id, cues in cues_by_page.items():
            previous: SubtitleSpan | None = None
            for cue in sorted(cues, key=lambda item: item.start_ms):
                if previous is not None and cue.start_ms < previous.end_ms:
                    issues.append(
                        _issue(
                            "subtitle_cue_overlap",
                            QualitySeverity.P1,
                            "同一页面的字幕 cue 时间重叠",
                            "重新切分字幕时间线，避免同时出现多个 cue",
                            RetryPolicy.RECOMPILE,
                            page_id=page_id,
                            start_ms=cue.start_ms,
                            end_ms=min(previous.end_ms, cue.end_ms),
                        )
                    )
                if previous is None or cue.end_ms > previous.end_ms:
                    previous = cue
        for placement in target.placements:
            if placement.page_id not in page_by_id:
                issues.append(
                    _issue(
                        "subtitle_placement_unknown_page",
                        QualitySeverity.P1,
                        "字幕布局引用了未知页面",
                        "重新生成字幕避让结果",
                        RetryPolicy.RECOMPILE,
                        page_id=placement.page_id,
                    )
                )
        placements_by_page: dict[UUID, list[SubtitlePlacement]] = {}
        for placement in target.placements:
            placements_by_page.setdefault(placement.page_id, []).append(placement)
        for page_id, placements in placements_by_page.items():
            for index, first in enumerate(placements):
                for second in placements[index + 1 :]:
                    if _rects_overlap(first.rect, second.rect):
                        issues.append(
                            _issue(
                                "subtitle_placement_overlap",
                                QualitySeverity.P1,
                                "同一页面的字幕布局区域发生重叠",
                                "重新计算字幕避让布局，避免文字互相遮挡",
                                RetryPolicy.RECOMPILE,
                                page_id=page_id,
                            )
                        )
        if target.placements and target.subtitles and target.pages:
            placed_page_ids = {item.page_id for item in target.placements}
            for page in page_by_id.values():
                if (
                    any(cue.page_id == page.page_id for cue in target.subtitles)
                    and page.page_id not in placed_page_ids
                ):
                    issues.append(
                        _issue(
                            "subtitle_placement_missing",
                            QualitySeverity.P1,
                            "字幕页面缺少已计算的安全区布局",
                            "重新计算字幕避让布局后再导出",
                            RetryPolicy.RECOMPILE,
                            page_id=page.page_id,
                        )
                    )
        return issues

    def _check_sync(self, target: QualityTarget, policy: QualityPolicy) -> list[QualityIssue]:
        if not target.audio_pages:
            return []
        visual_pages = {page.page_id: page for page in target.pages}
        audio_pages = {page.page_id: page for page in target.audio_pages}
        issues: list[QualityIssue] = []
        for page_id in audio_pages:
            if page_id not in visual_pages:
                issues.append(
                    _issue(
                        "audio_page_unknown",
                        QualitySeverity.P1,
                        "音频时间线引用了未知页面",
                        "重新编译音频页面时间线",
                        RetryPolicy.RECOMPILE,
                        page_id=page_id,
                    )
                )
        for page_id, visual_page in visual_pages.items():
            audio_page = audio_pages.get(page_id)
            if audio_page is None:
                issues.append(
                    _issue(
                        "audio_page_missing",
                        QualitySeverity.P1,
                        "视觉页面缺少对应音频时间线",
                        "补齐页面音频后重新编译",
                        RetryPolicy.RECOMPILE,
                        page_id=page_id,
                    )
                )
                continue
            start_drift = abs(audio_page.start_ms - visual_page.start_ms)
            end_drift = abs(audio_page.end_ms - visual_page.end_ms)
            if max(start_drift, end_drift) <= policy.sync_drift_tolerance_ms:
                continue
            range_start = min(audio_page.start_ms, visual_page.start_ms)
            range_end = max(audio_page.end_ms, visual_page.end_ms)
            issues.append(
                _issue(
                    "audio_visual_sync_drift",
                    QualitySeverity.P1,
                    "页面音频与视觉边界漂移超过策略阈值",
                    "重新编译页面时间线并检查音频尾部",
                    RetryPolicy.RECOMPILE,
                    page_id=page_id,
                    start_ms=range_start,
                    end_ms=max(range_start + 1, range_end),
                )
            )
        return issues

    def _sample_frames(self, target: QualityTarget) -> list[int]:
        samples: set[int] = {0}
        for page in target.pages:
            duration = page.end_ms - page.start_ms
            samples.update(
                max(0, min(target.expected_duration_ms, page.start_ms + round(duration * ratio)))
                for ratio in (0, 0.25, 0.5, 0.75, 1)
            )
        samples.add(max(0, target.expected_duration_ms))
        return sorted(samples)

    def _finish(
        self,
        project_id: UUID,
        render_job_id: UUID,
        target: QualityTarget,
        issues: list[QualityIssue],
        metrics: list[QualityMetric],
        sampled_frames: list[int],
        report_path: Path | None,
        report_relative_path: str | None,
        policy: QualityPolicy,
        blocks_p2: bool,
        render_provenance: Mapping[str, str] | None,
    ) -> QualityReport:
        fingerprint = canonical_hash(
            {
                "video_hash": file_hash(target.video_path) if target.video_path.is_file() else None,
                "target": target.model_dump(mode="json", exclude={"video_path"}),
                "policy": policy.model_dump(mode="json"),
                "analyzer_version": self.analyzer_version,
                "render_provenance": dict(render_provenance or {}),
            }
        )
        result = (
            QualityResult.BLOCKED
            if any(
                issue.severity in {QualitySeverity.P0, QualitySeverity.P1}
                or (blocks_p2 and issue.severity is QualitySeverity.P2)
                for issue in issues
            )
            else QualityResult.PASS_WITH_WARNINGS
            if issues
            else QualityResult.PASS
        )
        report = QualityReport(
            project_id=project_id,
            render_job_id=render_job_id,
            report_id=uuid4(),
            input_fingerprint=fingerprint,
            result=result,
            metrics=metrics,
            issues=issues,
            analyzer_versions={
                "quality-engine": self.analyzer_version,
                **dict(render_provenance or {}),
            },
            sampled_frames=sampled_frames,
            report_path=report_relative_path
            or (report_path.name if report_path is not None else None),
        )
        if report_path is not None:
            _write_report(report_path, report)
        return report


def _parse_probe(payload: dict[str, Any]) -> MediaProbe:
    streams = payload.get("streams", [])
    video: dict[str, Any] = next(
        (item for item in streams if item.get("codec_type") == "video"), {}
    )
    audio: dict[str, Any] = next(
        (item for item in streams if item.get("codec_type") == "audio"), {}
    )
    format_data = payload.get("format", {})
    return MediaProbe(
        width=video.get("width"),
        height=video.get("height"),
        fps=_parse_fps(video.get("r_frame_rate")),
        duration_ms=round(float(format_data.get("duration", 0)) * 1000)
        if format_data.get("duration") is not None
        else None,
        video_codec=video.get("codec_name"),
        audio_codec=audio.get("codec_name"),
        audio_channels=audio.get("channels"),
        audio_duration_ms=round(float(audio["duration"]) * 1000)
        if audio.get("duration") is not None
        else None,
        has_video=bool(video),
        has_audio=bool(audio),
    )


def _parse_fps(value: object) -> float | None:
    if not isinstance(value, str) or "/" not in value:
        return float(value) if isinstance(value, (int, float)) else None
    numerator, denominator = value.split("/", 1)
    try:
        return float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        return None


def _probe_metrics(probe: MediaProbe) -> list[QualityMetric]:
    return [
        QualityMetric(name="width", value=probe.width or 0, unit="px"),
        QualityMetric(name="height", value=probe.height or 0, unit="px"),
        QualityMetric(name="fps", value=probe.fps or 0, unit="fps"),
        QualityMetric(name="duration_ms", value=probe.duration_ms or 0, unit="ms"),
        QualityMetric(name="has_video", value=probe.has_video),
        QualityMetric(name="has_audio", value=probe.has_audio),
        QualityMetric(name="audio_channels", value=probe.audio_channels or 0),
        QualityMetric(name="audio_duration_ms", value=probe.audio_duration_ms or 0, unit="ms"),
    ]


def _parse_intervals(
    text: str,
    *,
    start_key: str,
    end_key: str,
    min_ms: int,
    code: str,
    message: str,
    action: str,
    severity: QualitySeverity,
) -> list[QualityIssue]:
    starts = [
        float(value) for value in re.findall(rf"{re.escape(start_key)}:\s*(-?\d+(?:\.\d+)?)", text)
    ]
    ends = [
        float(value) for value in re.findall(rf"{re.escape(end_key)}:\s*(-?\d+(?:\.\d+)?)", text)
    ]
    intervals: list[QualityIssue] = []
    for start, end in zip(starts, ends, strict=False):
        start_ms = max(0, round(start * 1000))
        end_ms = max(start_ms + 1, round(end * 1000))
        if end_ms - start_ms >= min_ms:
            intervals.append(
                _issue(
                    code,
                    severity,
                    message,
                    action,
                    RetryPolicy.NONE,
                    start_ms=start_ms,
                    end_ms=end_ms,
                )
            )
    return intervals


def _parse_scene_points(text: str, *, max_points: int = 64) -> list[int]:
    points: list[int] = []
    for value in _SCENE_POINT_RE.findall(text):
        point_ms = max(0, round(float(value) * 1000))
        if point_ms not in points:
            points.append(point_ms)
        if len(points) >= max_points:
            break
    return points


def _parse_frame_signatures(text: str, *, max_frames: int = 600) -> list[tuple[int, str]]:
    frames: list[tuple[int, str]] = []
    for line in text.splitlines():
        timestamp = _SCENE_POINT_RE.search(line)
        checksum = _FRAME_CHECKSUM_RE.search(line)
        if timestamp is None or checksum is None:
            continue
        frames.append((max(0, round(float(timestamp.group(1)) * 1000)), checksum.group(1).upper()))
        if len(frames) >= max_frames:
            break
    return frames


def _parse_loudness_value(text: str, marker: str) -> float | None:
    values = re.findall(rf"{marker}\s*(-?\d+(?:\.\d+)?)", text, flags=re.IGNORECASE)
    if not values:
        return None
    return float(values[-1])


def _dialogue_silence_issues(
    subtitles: list[SubtitleSpan],
    silence_issues: list[QualityIssue],
) -> list[QualityIssue]:
    dialogue_issues: list[QualityIssue] = []
    for silence in silence_issues:
        if silence.start_ms is None or silence.end_ms is None:
            continue
        for cue in subtitles:
            overlap_start = max(silence.start_ms, cue.start_ms)
            overlap_end = min(silence.end_ms, cue.end_ms)
            if overlap_end - overlap_start < 250:
                continue
            dialogue_issues.append(
                _issue(
                    "audio_missing_during_dialogue",
                    QualitySeverity.P1,
                    "对白区间内检测到异常静音",
                    "检查对应页面旁白或音频时间线",
                    RetryPolicy.REASSEMBLE,
                    page_id=cue.page_id,
                    start_ms=overlap_start,
                    end_ms=overlap_end,
                )
            )
            break
    return dialogue_issues


def _rects_overlap(first: NormalizedRect, second: NormalizedRect) -> bool:
    horizontal = min(first.x + first.width, second.x + second.width) - max(first.x, second.x)
    vertical = min(first.y + first.height, second.y + second.height) - max(first.y, second.y)
    return horizontal > 0 and vertical > 0


def _issue(
    code: str,
    severity: QualitySeverity,
    message: str,
    action: str,
    retry_policy: RetryPolicy,
    *,
    page_id: UUID | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> QualityIssue:
    return QualityIssue(
        code=code,
        severity=severity,
        scope=QualityScope.TIME_RANGE
        if start_ms is not None
        else QualityScope.PAGE
        if page_id
        else QualityScope.PROJECT,
        page_id=page_id,
        start_ms=start_ms,
        end_ms=end_ms,
        message=message,
        action=action,
        retry_policy=retry_policy,
    )


def _signal_analysis_failure(code: str) -> QualityIssue:
    return _issue(
        code,
        QualitySeverity.P1,
        "无法完成媒体信号分析",
        "检查 FFmpeg 运行时和成片完整性后重试",
        RetryPolicy.NONE,
    )


def _write_report(path: Path, report: QualityReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _subprocess_runner(command: Sequence[str], cwd: Path) -> QualityProcessResult:
    completed = subprocess.run(
        list(command),
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        check=False,
    )
    return QualityProcessResult(
        returncode=completed.returncode,
        stdout=completed.stdout[-64 * 1024 :],
        stderr=completed.stderr[-64 * 1024 :],
    )
