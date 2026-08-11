from uuid import UUID

from workbench.domain.presenter import PresenterSegment, PresenterTimelineV1
from workbench.video.models import ProjectVideoProps, VideoPageProps


def test_presenter_render_contract_has_one_master_source_and_continuous_duration() -> None:
    timeline = PresenterTimelineV1(
        source_id=UUID(int=5),
        source_version="a" * 64,
        duration_ms=4_000,
        timeline_hash="b" * 64,
        segments=[
            PresenterSegment(start_ms=0, end_ms=1_000, layout="top_right", width_ratio=0.22),
            PresenterSegment(start_ms=1_000, end_ms=4_000, layout="hidden", width_ratio=0),
        ],
    )
    props = ProjectVideoProps(
        project_id=UUID(int=1),
        duration_ms=4_000,
        template_version="tech-board-v1",
        pages=[
            VideoPageProps(
                page_id=UUID(int=2),
                page_order=1,
                image_path="page.png",
                audio_path="unused.wav",
                start_ms=0,
                end_ms=4_000,
            )
        ],
        presenter_timeline=timeline,
        presenter_source_path="presenter/source.mp4",
        timeline_revision=1,
        timeline_hash="b" * 64,
    )
    exported = props.model_dump(mode="json")
    assert exported["presenter_source_path"] == "presenter/source.mp4"
    assert exported["duration_ms"] == exported["presenter_timeline"]["duration_ms"]
    assert exported["presenter_timeline"]["segments"][1]["layout"] == "hidden"
