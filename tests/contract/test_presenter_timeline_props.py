from uuid import UUID

from workbench.domain.presenter import PresenterTimelineV1
from workbench.video.models import ProjectVideoProps, VideoPageProps


def test_preview_and_render_props_share_same_timeline_hash() -> None:
    timeline = PresenterTimelineV1(
        source_id=UUID(int=9),
        source_version="a" * 64,
        duration_ms=2_000,
        timeline_hash="b" * 64,
    )
    payload = dict(
        project_id=UUID(int=1),
        duration_ms=2_000,
        template_version="tech-board-v1",
        pages=[
            VideoPageProps(
                page_id=UUID(int=2),
                page_order=1,
                image_path="page.png",
                audio_path="audio.wav",
                start_ms=0,
                end_ms=2_000,
            )
        ],
        presenter_timeline=timeline,
        presenter_source_path="presenter/source.mp4",
        timeline_revision=timeline.revision,
        timeline_hash=timeline.timeline_hash,
    )
    preview = ProjectVideoProps(**payload)
    render = ProjectVideoProps.model_validate_json(preview.model_dump_json())
    assert preview.timeline_hash == render.timeline_hash == timeline.timeline_hash
    assert preview.timeline_revision == render.timeline_revision == 1
