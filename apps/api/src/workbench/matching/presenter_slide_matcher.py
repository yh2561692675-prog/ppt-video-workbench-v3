from __future__ import annotations

from difflib import SequenceMatcher
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from workbench.domain.transcript import PresenterTranscriptSentence

from .text_normalization import normalize_presenter_text, text_features


class MatchContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PresenterMatchPage(MatchContract):
    page_id: UUID
    page_index: int = Field(ge=0)
    title: str = ""
    slide_text: str = ""
    narration_text: str = ""
    chapter_terms: list[str] = Field(default_factory=list)


class PresenterMatchCandidate(MatchContract):
    page_id: UUID
    page_index: int = Field(ge=0)
    sentence_ids: list[str] = Field(min_length=1)
    score: float = Field(ge=0, le=1)
    evidence: dict[str, float | bool | str]
    warnings: list[str] = Field(default_factory=list)


class PresenterMatchResult(MatchContract):
    matches: list[PresenterMatchCandidate] = Field(default_factory=list)
    unassigned_sentence_ids: list[str] = Field(default_factory=list)


def match_presenter_to_slides(
    sentences: list[PresenterTranscriptSentence],
    pages: list[PresenterMatchPage],
    *,
    locked: dict[str, UUID] | None = None,
    minimum_score: float = 0.15,
) -> PresenterMatchResult:
    ordered_pages = sorted(pages, key=lambda item: item.page_index)
    page_by_id = {item.page_id: item for item in ordered_pages}
    locked_pages = locked or {}
    matches: list[PresenterMatchCandidate] = []
    unassigned: list[str] = []
    minimum_page_index = 0
    for sentence in sentences:
        locked_page_id = locked_pages.get(sentence.id)
        if locked_page_id is not None:
            selected = page_by_id.get(locked_page_id)
            if selected is None:
                unassigned.append(sentence.id)
                continue
            score, evidence = _score(sentence, selected, previous_index=minimum_page_index)
            evidence["manual_lock"] = True
        else:
            candidates = [item for item in ordered_pages if item.page_index >= minimum_page_index]
            if not candidates:
                unassigned.append(sentence.id)
                continue
            ranked = [
                (*_score(sentence, page, previous_index=minimum_page_index), page)
                for page in candidates
            ]
            score, evidence, selected = max(
                ranked,
                key=lambda item: (item[0], -item[2].page_index),
            )
            if score < minimum_score:
                unassigned.append(sentence.id)
                continue
        matches.append(
            PresenterMatchCandidate(
                page_id=selected.page_id,
                page_index=selected.page_index,
                sentence_ids=[sentence.id],
                score=round(score, 4),
                evidence=evidence,
                warnings=[] if score >= 0.55 else ["low_confidence"],
            )
        )
        if locked_page_id is None:
            minimum_page_index = selected.page_index
    return PresenterMatchResult(matches=matches, unassigned_sentence_ids=unassigned)


def _score(
    sentence: PresenterTranscriptSentence,
    page: PresenterMatchPage,
    *,
    previous_index: int,
) -> tuple[float, dict[str, float | bool | str]]:
    sentence_text = normalize_presenter_text(sentence.text)
    title = normalize_presenter_text(page.title)
    slide = normalize_presenter_text(page.slide_text)
    narration = normalize_presenter_text(page.narration_text)
    page_text = " ".join(item for item in (title, slide, narration) if item)
    sentence_features = text_features(sentence_text)
    page_features = text_features(page_text)
    union = sentence_features | page_features
    overlap = len(sentence_features & page_features) / len(union) if union else 0.0
    sequence = SequenceMatcher(None, sentence_text, page_text).ratio() if page_text else 0.0
    title_hit = 1.0 if title and title.replace(" ", "") in sentence_text.replace(" ", "") else 0.0
    chapter_hit = (
        1.0
        if any(normalize_presenter_text(term) in sentence_text for term in page.chapter_terms)
        else 0.0
    )
    order_bonus = 1.0 if page.page_index == previous_index else 0.0
    score = min(
        1.0,
        overlap * 0.5 + sequence * 0.2 + title_hit * 0.2 + chapter_hit * 0.05 + order_bonus * 0.05,
    )
    return score, {
        "slide_similarity": round(overlap, 4),
        "sequence_similarity": round(sequence, 4),
        "title_hit": bool(title_hit),
        "chapter_hit": bool(chapter_hit),
        "order_bonus": bool(order_bonus),
    }
