from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from workbench.domain.models import ProjectManifest
from workbench.domain.presenter import PresenterSegment, PresenterTimelineV1, PresenterTimeRange
from workbench.timeline.presenter_builder import timeline_content_hash


class PresenterFallbackContract(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


class PresenterFallbackIssue(PresenterFallbackContract):
    code: Literal["PRESENTER_LAYER_RENDER_FAILED"] = "PRESENTER_LAYER_RENDER_FAILED"
    level: Literal["warning"] = "warning"
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    reason: str
    action: str = "该区间已降级为 PPT、字幕与真人主音轨，建议检查小窗素材后局部重渲染"
    blocking: bool = False


class PresenterFallbackResult(PresenterFallbackContract):
    status: Literal["completed", "degraded"]
    audio_track: Literal["presenter_master"]
    slide_video_complete: bool
    subtitles_preserved: bool = True
    project: ProjectManifest
    issues: list[PresenterFallbackIssue] = Field(default_factory=list)


class PresenterLayerRenderError(RuntimeError):
    def __init__(self, failed_ranges: list[PresenterTimeRange], reason: str) -> None:
        super().__init__(reason)
        self.failed_ranges = failed_ranges
        self.reason = reason


def fallback_to_audio_slides(
    project: ProjectManifest,
    failed_ranges: list[PresenterTimeRange],
    *,
    reason: str = "presenter layer render failed",
) -> PresenterFallbackResult:
    timeline = project.presenter_timeline
    if project.presenter_source is None or timeline is None:
        raise ValueError("presenter fallback requires source and timeline")
    segments = [
        _hide_failed_segment(segment, failed_ranges, timeline.source_version)
        for segment in timeline.segments
    ]
    degraded_timeline = PresenterTimelineV1.model_validate(
        timeline.model_copy(
            update={"segments": segments, "revision": timeline.revision + 1}
        ).model_dump(mode="python")
    )
    degraded_timeline = degraded_timeline.model_copy(
        update={"timeline_hash": timeline_content_hash(degraded_timeline)}
    )
    payload = project.model_dump(mode="python")
    payload["presenter_timeline"] = degraded_timeline
    degraded_project = ProjectManifest.model_validate(payload)
    return PresenterFallbackResult(
        status="degraded",
        audio_track="presenter_master",
        slide_video_complete=True,
        project=degraded_project,
        issues=[
            PresenterFallbackIssue(
                start_ms=item.start_ms,
                end_ms=item.end_ms,
                reason=reason,
            )
            for item in failed_ranges
        ],
    )


def render_with_presenter_fallback(
    project: ProjectManifest,
    render_presenter: Callable[[ProjectManifest], None],
    render_slides: Callable[[ProjectManifest], bool],
) -> PresenterFallbackResult:
    try:
        render_presenter(project)
    except PresenterLayerRenderError as error:
        result = fallback_to_audio_slides(project, error.failed_ranges, reason=error.reason)
        return result.model_copy(update={"slide_video_complete": render_slides(result.project)})
    return PresenterFallbackResult(
        status="completed",
        audio_track="presenter_master",
        slide_video_complete=True,
        project=project,
    )


def _hide_failed_segment(
    segment: PresenterSegment,
    failed_ranges: list[PresenterTimeRange],
    source_version: str,
) -> PresenterSegment:
    failed = any(
        segment.start_ms < item.end_ms and segment.end_ms > item.start_ms for item in failed_ranges
    )
    if not failed:
        return segment
    return segment.model_copy(
        update={
            "layout": "hidden",
            "width_ratio": 0,
            "source_revision": segment.source_revision or source_version,
        }
    )
