from datetime import UTC, datetime
from uuid import UUID

from workbench.domain.models import ProjectManifest
from workbench.domain.presenter import (
    PresentationMode,
    PresenterSegment,
    PresenterSource,
    PresenterTimelineV1,
    PresenterTimeRange,
)
from workbench.rendering.exporter import (
    PresenterLayerRenderError,
    render_with_presenter_fallback,
)


def _project() -> ProjectManifest:
    now = datetime.now(UTC)
    source = PresenterSource(
        id=UUID(int=2),
        relative_path="presenter/source.mp4",
        sha256="a" * 64,
        duration_ms=4_000,
    )
    timeline = PresenterTimelineV1(
        source_id=source.id,
        source_version=source.sha256,
        duration_ms=4_000,
        timeline_hash="b" * 64,
        segments=[
            PresenterSegment(
                start_ms=0,
                end_ms=4_000,
                layout="top_right",
                width_ratio=0.22,
            )
        ],
    )
    return ProjectManifest(
        id=UUID(int=1),
        name="presenter",
        project_dir="presenter",
        created_at=now,
        updated_at=now,
        presentation_mode=PresentationMode.HUMAN_PRESENTER,
        presenter_source=source,
        presenter_timeline=timeline,
    )


def test_presenter_video_failure_keeps_master_audio_and_slides() -> None:
    rendered_projects: list[ProjectManifest] = []

    def fail(_: ProjectManifest) -> None:
        raise PresenterLayerRenderError(
            [PresenterTimeRange(start_ms=1_000, end_ms=2_000)],
            "injected presenter decoder failure",
        )

    result = render_with_presenter_fallback(
        _project(), fail, lambda project: rendered_projects.append(project) is None
    )

    assert result.status == "degraded"
    assert result.audio_track == "presenter_master"
    assert result.slide_video_complete is True
    assert result.subtitles_preserved is True
    assert result.project.presenter_timeline.segments[0].layout == "hidden"
    assert result.issues[0].code == "PRESENTER_LAYER_RENDER_FAILED"
    assert result.issues[0].blocking is False
    assert rendered_projects == [result.project]
