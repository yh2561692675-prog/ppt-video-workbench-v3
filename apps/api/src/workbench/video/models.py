from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from workbench.domain.presenter import PresenterTimelineV1
from workbench.effects.schema import EffectPlanV2
from workbench.subtitles.models import SubtitleCue


class VideoModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


# These are the video canvases that the V1 page renderer can produce without
# an implicit post-render scale.  Keep this list deliberately small: accepting
# arbitrary dimensions would make a queued job look valid even though the
# renderer and package validator have never been qualified for it.
STANDARD_VIDEO_CANVASES = frozenset(
    {
        (1280, 720),
        (1920, 1080),
        (720, 1280),
        (1080, 1920),
        (720, 720),
        (1080, 1080),
        (3840, 2160),
    }
)
STANDARD_VIDEO_FPS = frozenset({24, 25, 30, 60})


class TextRect(VideoModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class SubtitlePlacement(VideoModel):
    page_id: UUID
    position: Literal["top", "middle", "bottom", "fallback-panel"]
    rect: TextRect
    panel: bool = False
    reason: str | None = None


class VideoPageProps(VideoModel):
    page_id: UUID
    page_order: int = Field(ge=1)
    title: str = ""
    image_path: str
    audio_path: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    subtitle_cue_ids: list[UUID] = Field(default_factory=list)
    effect_plan: EffectPlanV2 | None = None
    effect_plan_revision: int | None = Field(default=None, ge=1)
    effect_plan_hash: str | None = None

    @model_validator(mode="after")
    def validate_range(self) -> VideoPageProps:
        if self.end_ms <= self.start_ms:
            raise ValueError("视频页面结束时间必须晚于开始时间")
        return self


class ProjectVideoProps(VideoModel):
    schema_version: Literal[1, 2] = 1
    project_id: UUID
    width: int = Field(default=1920, gt=0, le=3840)
    height: int = Field(default=1080, gt=0, le=2160)
    fps: int = Field(default=30, gt=0, le=60)
    duration_ms: int = Field(ge=0)
    template_version: str = Field(min_length=1)
    reduced_motion: bool = False
    pages: list[VideoPageProps] = Field(min_length=1)
    subtitles: list[SubtitleCue] = Field(default_factory=list)
    subtitle_placements: list[SubtitlePlacement] = Field(default_factory=list)
    catalog_version: str | None = None
    presenter_timeline: PresenterTimelineV1 | None = None
    presenter_source_path: str | None = None
    timeline_revision: int | None = Field(default=None, ge=1)
    timeline_hash: str | None = None

    @model_validator(mode="after")
    def validate_pages(self) -> ProjectVideoProps:
        if (self.width, self.height) not in STANDARD_VIDEO_CANVASES:
            raise ValueError(
                "video canvas must be one of the qualified 720p/1080p profiles or 4K 16:9"
            )
        if self.fps not in STANDARD_VIDEO_FPS:
            raise ValueError("video fps must be one of 24, 25, 30, or 60")
        if self.presenter_timeline is None:
            if any(
                value is not None
                for value in (
                    self.presenter_source_path,
                    self.timeline_revision,
                    self.timeline_hash,
                )
            ):
                raise ValueError("presenter timeline metadata requires presenter_timeline")
        else:
            if not self.presenter_source_path:
                raise ValueError("presenter timeline requires presenter_source_path")
            if self.timeline_revision != self.presenter_timeline.revision:
                raise ValueError("presenter timeline revision mismatch")
            if self.timeline_hash != self.presenter_timeline.timeline_hash:
                raise ValueError("presenter timeline hash mismatch")
        orders = [page.page_order for page in self.pages]
        if orders != sorted(orders) or orders != list(range(1, len(orders) + 1)):
            raise ValueError("页面顺序必须从 1 连续递增")
        previous_end = 0
        for page in self.pages:
            if page.start_ms < previous_end or page.end_ms > self.duration_ms:
                raise ValueError("页面时间轴必须有序且位于项目时长内")
            previous_end = page.end_ms
        page_ids = {page.page_id for page in self.pages}
        placement_page_ids = [placement.page_id for placement in self.subtitle_placements]
        if set(placement_page_ids) - page_ids:
            raise ValueError("字幕避让结果包含未知页面")
        if len(placement_page_ids) != len(set(placement_page_ids)):
            raise ValueError("每页只能有一条字幕避让结果")
        return self

    @property
    def duration_in_frames(self) -> int:
        return ms_to_frames(self.duration_ms, self.fps)


class PreflightIssue(VideoModel):
    code: str
    message: str
    action: str
    page_id: UUID | None = None
    blocking: bool = True


class VideoPreflight(VideoModel):
    allowed: bool
    issues: list[PreflightIssue] = Field(default_factory=list)
    placements: list[SubtitlePlacement] = Field(default_factory=list)
    props: ProjectVideoProps | None = None


def ms_to_frames(milliseconds: int, fps: int) -> int:
    if milliseconds < 0 or fps <= 0:
        raise ValueError("毫秒数和 FPS 必须为正数或零")
    return (milliseconds * fps + 500) // 1_000
