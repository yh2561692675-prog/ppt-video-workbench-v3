from uuid import UUID

import pytest
from workbench.domain.presenter import PresenterTimelineV1, SlideAnchor
from workbench.domain.transcript import PresenterTranscriptSentence
from workbench.matching.presenter_slide_matcher import (
    PresenterMatchCandidate,
    PresenterMatchResult,
)
from workbench.timeline.presenter_builder import (
    build_presenter_timeline,
    classify_confidence,
    recalculate_unlocked,
)


@pytest.mark.parametrize(
    ("score", "status"),
    [(0.95, "auto"), (0.85, "review"), (0.79, "blocked")],
)
def test_confidence_status(score: float, status: str) -> None:
    assert classify_confidence(score) == status


def _sentence(identifier: str, start_ms: int, end_ms: int) -> PresenterTranscriptSentence:
    return PresenterTranscriptSentence(
        id=identifier,
        text=identifier,
        normalized_text=identifier,
        start_ms=start_ms,
        end_ms=end_ms,
    )


def test_builder_uses_monotonic_gapless_page_anchors_and_tracks_unassigned() -> None:
    result = PresenterMatchResult(
        matches=[
            PresenterMatchCandidate(
                page_id=UUID(int=1), page_index=0, sentence_ids=["s1"], score=0.95, evidence={}
            ),
            PresenterMatchCandidate(
                page_id=UUID(int=2), page_index=1, sentence_ids=["s3"], score=0.85, evidence={}
            ),
        ],
        unassigned_sentence_ids=["s2"],
    )
    timeline = build_presenter_timeline(
        result,
        [_sentence("s1", 500, 1_500), _sentence("s2", 1_600, 2_200), _sentence("s3", 2_500, 3_500)],
        4_000,
        source_id=UUID(int=9),
        source_version="a" * 64,
    )

    assert timeline.anchors[0].start_ms == 0
    assert timeline.anchors[0].end_ms == timeline.anchors[1].start_ms
    assert timeline.anchors[-1].end_ms == 4_000
    assert timeline.unassigned_ranges[0].reason == "unassigned_sentence:s2"
    assert timeline.timeline_hash and len(timeline.timeline_hash) == 64


def test_local_recalculation_preserves_locks_and_non_adjacent_anchors() -> None:
    anchors = [
        SlideAnchor(
            page_id=UUID(int=index + 1),
            start_ms=index * 1_000,
            end_ms=(index + 1) * 1_000,
            confidence=0.95,
            status="auto",
            manual_lock=index == 0,
            source_revision="a" * 64,
        )
        for index in range(4)
    ]
    timeline = PresenterTimelineV1(
        source_id=UUID(int=9), source_version="a" * 64, duration_ms=4_000, anchors=anchors
    )
    replacement = anchors[2].model_copy(update={"start_ms": 2_100, "end_ms": 3_100})

    updated = recalculate_unlocked(timeline, anchors[2].page_id, replacement)

    assert updated.anchors[0] == timeline.anchors[0]
    assert updated.anchors[1].end_ms == 2_100
    assert updated.anchors[3].start_ms == 3_100


def test_local_recalculation_never_changes_a_locked_target() -> None:
    locked = SlideAnchor(
        page_id=UUID(int=1),
        start_ms=0,
        end_ms=1_000,
        confidence=1,
        status="confirmed",
        manual_lock=True,
        source_revision="a" * 64,
    )
    timeline = PresenterTimelineV1(
        source_id=UUID(int=9), source_version="a" * 64, duration_ms=1_000, anchors=[locked]
    )
    assert (
        recalculate_unlocked(
            timeline,
            locked.page_id,
            locked.model_copy(update={"end_ms": 900}),
        )
        is timeline
    )
