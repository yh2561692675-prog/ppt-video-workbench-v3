from uuid import UUID

from workbench.domain.presenter import SlideAnchor
from workbench.domain.transcript import (
    PresenterTranscriptSentence,
    PresenterTranscriptWord,
    TranscriptRevision,
)
from workbench.matching.presenter_slide_matcher import (
    PresenterMatchCandidate,
    PresenterMatchResult,
)
from workbench.timeline.presenter_adapters import to_caption_cues, to_effect_cues


def _transcript() -> TranscriptRevision:
    return TranscriptRevision(
        id=UUID(int=20),
        source_hash="a" * 64,
        audio_hash="b" * 64,
        duration_ms=2_000,
        detected_language="zh",
        model_version="test",
        glossary_version="1",
        cache_key="c" * 64,
        content_hash="d" * 64,
        words=[
            PresenterTranscriptWord(
                id="w1",
                text="hello",
                normalized_text="hello",
                start_ms=100,
                end_ms=400,
                confidence=0.99,
            )
        ],
        sentences=[
            PresenterTranscriptSentence(
                id="s1",
                text="hello",
                normalized_text="hello",
                start_ms=100,
                end_ms=400,
                word_ids=["w1"],
            )
        ],
    )


def test_caption_adapter_keeps_sentence_and_word_timing() -> None:
    anchor = SlideAnchor(
        page_id=UUID(int=1),
        start_ms=0,
        end_ms=2_000,
        sentence_ids=["s1"],
        confidence=0.95,
        status="auto",
    )
    cue = to_caption_cues(_transcript(), [anchor])[0]
    assert (cue.start_ms, cue.end_ms) == (100, 400)
    assert cue.source_word_indexes == [0]


def test_low_confidence_effect_cue_requests_safe_template() -> None:
    anchor = SlideAnchor(
        page_id=UUID(int=1),
        start_ms=0,
        end_ms=2_000,
        sentence_ids=["s1"],
        confidence=0.7,
        status="blocked",
    )
    matches = PresenterMatchResult(
        matches=[
            PresenterMatchCandidate(
                page_id=UUID(int=1), page_index=0, sentence_ids=["s1"], score=0.7, evidence={}
            )
        ]
    )
    cue = to_effect_cues(matches, [anchor])[0]
    assert cue.template == "SafeSlide"
    assert (cue.start_ms, cue.end_ms) == (0, 2_000)
