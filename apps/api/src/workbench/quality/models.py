from __future__ import annotations

from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class QualityResult(StrEnum):
    PASS = "pass"
    PASS_WITH_WARNINGS = "pass_with_warnings"
    BLOCKED = "blocked"


class QualitySeverity(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class QualityScope(StrEnum):
    PROJECT = "project"
    PAGE = "page"
    TIME_RANGE = "time_range"
    ARTIFACT = "artifact"


class RetryPolicy(StrEnum):
    NONE = "none"
    RERENDER_PAGE = "rerender_page"
    REASSEMBLE = "reassemble"
    RECOMPILE = "recompile"


class QualityModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _is_unsafe_relative_path(value: str) -> bool:
    """Reject absolute and parent paths in both supported path syntaxes."""

    windows_path = PureWindowsPath(value)
    posix_path = PurePosixPath(value)
    return (
        windows_path.is_absolute()
        or posix_path.is_absolute()
        or ".." in windows_path.parts
        or ".." in posix_path.parts
    )


class PageSpan(QualityModel):
    page_id: UUID
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> PageSpan:
        if self.end_ms <= self.start_ms:
            raise ValueError("页面结束时间必须晚于开始时间")
        return self


class SubtitleSpan(QualityModel):
    cue_id: UUID
    page_id: UUID
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text_length: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> SubtitleSpan:
        if self.end_ms <= self.start_ms:
            raise ValueError("字幕结束时间必须晚于开始时间")
        return self


class NormalizedRect(QualityModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> NormalizedRect:
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("矩形必须位于规范化画布内")
        return self


class SubtitlePlacement(QualityModel):
    page_id: UUID
    rect: NormalizedRect
    panel: bool = False


class QualityTarget(QualityModel):
    video_path: Path
    expected_width: int = Field(default=1920, gt=0)
    expected_height: int = Field(default=1080, gt=0)
    expected_fps: float = Field(default=30, gt=0)
    expected_video_codec: str = "h264"
    expected_audio_codec: str = "aac"
    expected_audio_channels: int | None = Field(default=None, gt=0)
    expected_duration_ms: int = Field(ge=0)
    duration_tolerance_ms: int = Field(default=100, ge=0)
    pages: list[PageSpan] = Field(default_factory=list)
    audio_pages: list[PageSpan] = Field(default_factory=list)
    subtitles: list[SubtitleSpan] = Field(default_factory=list)
    placements: list[SubtitlePlacement] = Field(default_factory=list)


class QualityPolicy(QualityModel):
    schema_version: Literal["1.0"] = "1.0"
    name: Literal["strict", "standard", "fast"] = "standard"
    black_frame_min_ms: int = Field(default=500, ge=1)
    freeze_min_ms: int = Field(default=500, ge=1)
    silence_min_ms: int = Field(default=1000, ge=1)
    min_integrated_lufs: float = Field(default=-30.0, ge=-100.0, le=0.0)
    max_true_peak_db: float = Field(default=-0.1, ge=-20.0, le=10.0)
    sync_drift_tolerance_ms: int = Field(default=500, ge=0)
    max_subtitle_text_length: int = Field(default=80, ge=1)
    p2_blocks: bool = False

    @classmethod
    def preset(cls, name: Literal["strict", "standard", "fast"]) -> QualityPolicy:
        """Return the versioned built-in policy fixture for a named mode."""

        if name == "strict":
            return cls(
                name="strict",
                black_frame_min_ms=300,
                freeze_min_ms=300,
                silence_min_ms=700,
                max_subtitle_text_length=60,
                p2_blocks=True,
            )
        if name == "fast":
            return cls(
                name="fast",
                black_frame_min_ms=1_000,
                freeze_min_ms=1_000,
                silence_min_ms=1_500,
                max_subtitle_text_length=100,
                p2_blocks=False,
            )
        return cls(name="standard")


class QualityMetric(QualityModel):
    name: str = Field(min_length=1, max_length=100)
    value: float | int | str | bool
    unit: str | None = Field(default=None, max_length=32)


class EvidenceRef(QualityModel):
    relative_path: str = Field(min_length=1, max_length=300)
    kind: Literal["frame", "audio", "log", "json"]
    page_id: UUID | None = None
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_relative_path(self) -> EvidenceRef:
        if _is_unsafe_relative_path(self.relative_path):
            raise ValueError("证据路径必须位于项目相对目录内")
        if self.start_ms is not None and self.end_ms is not None and self.end_ms <= self.start_ms:
            raise ValueError("证据结束时间必须晚于开始时间")
        return self


class QualityIssue(QualityModel):
    issue_id: UUID = Field(default_factory=uuid4)
    code: str = Field(min_length=1, max_length=80)
    severity: QualitySeverity
    scope: QualityScope
    page_id: UUID | None = None
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    message: str = Field(min_length=1, max_length=500)
    action: str = Field(min_length=1, max_length=500)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    retry_policy: RetryPolicy = RetryPolicy.NONE

    @model_validator(mode="after")
    def validate_time_range(self) -> QualityIssue:
        if (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("问题时间范围必须同时提供开始和结束时间")
        if self.start_ms is not None and self.end_ms is not None and self.end_ms <= self.start_ms:
            raise ValueError("问题结束时间必须晚于开始时间")
        if self.scope is QualityScope.PAGE and self.page_id is None:
            raise ValueError("页面问题必须包含 page_id")
        if self.scope is QualityScope.TIME_RANGE and self.start_ms is None:
            raise ValueError("时间范围问题必须包含时间区间")
        return self


class QualityReport(QualityModel):
    schema_version: Literal["1.0"] = "1.0"
    project_id: UUID
    render_job_id: UUID
    report_id: UUID
    input_fingerprint: str = Field(min_length=64, max_length=64)
    result: QualityResult
    metrics: list[QualityMetric] = Field(default_factory=list)
    issues: list[QualityIssue] = Field(default_factory=list)
    analyzer_versions: dict[str, str] = Field(default_factory=dict)
    sampled_frames: list[int] = Field(default_factory=list)
    report_path: str | None = None

    @model_validator(mode="after")
    def validate_report_path(self) -> QualityReport:
        if self.report_path is not None and _is_unsafe_relative_path(self.report_path):
            raise ValueError("质量报告路径必须为项目相对路径")
        return self


class MediaProbe(QualityModel):
    width: int | None = Field(default=None, ge=0)
    height: int | None = Field(default=None, ge=0)
    fps: float | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0)
    video_codec: str | None = None
    audio_codec: str | None = None
    audio_channels: int | None = Field(default=None, ge=0)
    audio_duration_ms: int | None = Field(default=None, ge=0)
    has_video: bool = False
    has_audio: bool = False


def as_json_value(value: Any) -> Any:
    """Keep this helper local so evidence payloads cannot contain Path objects."""

    if isinstance(value, Path):
        return value.as_posix()
    return value
