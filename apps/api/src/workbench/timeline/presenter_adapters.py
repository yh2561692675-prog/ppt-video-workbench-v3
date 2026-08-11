from __future__ import annotations

from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field

from workbench.domain.presenter import SlideAnchor
from workbench.domain.transcript import TranscriptRevision
from workbench.matching.presenter_slide_matcher import PresenterMatchResult
from workbench.subtitles.models import SubtitleCue


class PresenterContentCue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_id: str = Field(min_length=1)
    page_id: UUID
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    confidence: float = Field(ge=0, le=1)
    template: str


def to_caption_cues(
    transcript: TranscriptRevision,
    anchors: list[SlideAnchor],
) -> list[SubtitleCue]:
    sentence_by_id = {item.id: item for item in transcript.sentences}
    word_index = {word.id: index for index, word in enumerate(transcript.words)}
    cues: list[SubtitleCue] = []
    for page_order, anchor in enumerate(anchors, start=1):
        for sentence_id in anchor.sentence_ids:
            sentence = sentence_by_id.get(sentence_id)
            if sentence is None or not sentence.text.strip():
                continue
            source_indexes = [word_index[item] for item in sentence.word_ids if item in word_index]
            if not source_indexes:
                source_indexes = [len(cues)]
            cues.append(
                SubtitleCue(
                    id=uuid5(transcript.id, f"caption:{anchor.page_id}:{sentence.id}"),
                    page_id=anchor.page_id,
                    page_order=page_order,
                    start_ms=sentence.start_ms,
                    end_ms=sentence.end_ms,
                    text=sentence.text.strip(),
                    source_word_indexes=source_indexes,
                )
            )
    return sorted(cues, key=lambda item: (item.start_ms, item.end_ms, str(item.id)))


def to_effect_cues(
    matches: PresenterMatchResult,
    anchors: list[SlideAnchor],
) -> list[PresenterContentCue]:
    score_by_page = {candidate.page_id: candidate.score for candidate in matches.matches}
    return [
        PresenterContentCue(
            module_id=f"presenter-page-{anchor.page_id}",
            page_id=anchor.page_id,
            start_ms=anchor.start_ms,
            end_ms=anchor.end_ms,
            confidence=score_by_page.get(anchor.page_id, anchor.confidence),
            template=(
                "SafeSlide"
                if score_by_page.get(anchor.page_id, anchor.confidence) < 0.8
                else "FocusSpotlight"
            ),
        )
        for anchor in anchors
    ]
