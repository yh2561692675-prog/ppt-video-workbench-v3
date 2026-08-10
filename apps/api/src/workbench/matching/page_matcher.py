from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from workbench.domain.extraction import PageExtraction
from workbench.domain.matching import (
    MatchCandidate,
    MatchComponents,
    MatchPlan,
    MatchWeights,
    PageMatch,
)
from workbench.domain.outline import OutlineDocument

MIN_ACCEPTED_SCORE = 0.55
WEIGHTS = MatchWeights()


@dataclass(frozen=True)
class _Section:
    order: int
    source_ref: str
    title: str
    body: str

    @property
    def text(self) -> str:
        return "\n".join(value for value in (self.title, self.body) if value)


def match_outline_to_pages(outline: OutlineDocument, pages: list[PageExtraction]) -> MatchPlan:
    sections = _sections(outline)
    duplicate_texts = _duplicate_texts(pages)
    matches: list[PageMatch] = []
    for page in sorted(pages, key=lambda item: item.order):
        candidates = [
            _score_candidate(page, section, max(len(pages), len(sections))) for section in sections
        ]
        candidates.sort(key=lambda item: (-item.score, item.outline_ref))
        selected = candidates[0] if candidates else None
        conflicts: list[str] = []
        normalized_page = _normalize(page.text)
        if not normalized_page:
            conflicts.append("empty_page")
        if normalized_page and normalized_page in duplicate_texts:
            conflicts.append("duplicate_page_content")
        if selected and page.title and selected.components.title < 0.20:
            conflicts.append("title_conflict")
        score = selected.score if selected else 0.0
        matches.append(
            PageMatch(
                page_id=page.id,
                page_order=page.order,
                page_title=page.title,
                page_text=page.text,
                preview_path=str(page.preview_path) if page.preview_path else None,
                selected_outline_ref=selected.outline_ref if selected else None,
                score=score,
                needs_confirmation=score < MIN_ACCEPTED_SCORE or bool(conflicts),
                conflicts=conflicts,
                decision_source="deterministic_rules",
                candidates=candidates,
            )
        )
    return MatchPlan(matches=matches)


def _sections(outline: OutlineDocument) -> list[_Section]:
    sections: list[_Section] = []
    current_title = ""
    current_ref = ""
    body: list[str] = []
    for block in outline.blocks:
        if block.kind == "heading":
            if current_title or body:
                sections.append(
                    _Section(len(sections) + 1, current_ref, current_title, "\n".join(body))
                )
            current_title = block.text
            current_ref = block.source_ref
            body = []
        else:
            if not current_ref:
                current_ref = block.source_ref
            body.append(block.text)
    if current_title or body:
        sections.append(_Section(len(sections) + 1, current_ref, current_title, "\n".join(body)))
    return sections


def _score_candidate(page: PageExtraction, section: _Section, count: int) -> MatchCandidate:
    denominator = max(count - 1, 1)
    order_score = max(0.0, 1.0 - abs(page.order - section.order) / denominator)
    page_title = page.title or ""
    page_body = page.text
    if page_title and page_body.startswith(page_title):
        page_body = page_body[len(page_title) :].lstrip()
    components = MatchComponents(
        page_order=_rounded(order_score),
        title=_rounded(_similarity(page_title, section.title)),
        keywords=_rounded(_keyword_overlap(page.text, section.text)),
        body=_rounded(_similarity(page_body, section.body)),
    )
    score = (
        components.page_order * WEIGHTS.page_order
        + components.title * WEIGHTS.title
        + components.keywords * WEIGHTS.keywords
        + components.body * WEIGHTS.body
    )
    return MatchCandidate(
        outline_ref=section.source_ref,
        outline_title=section.title,
        outline_text=section.text,
        score=_rounded(score),
        weights=WEIGHTS,
        components=components,
    )


def _similarity(left: str, right: str) -> float:
    left_normalized = _normalize(left)
    right_normalized = _normalize(right)
    if not left_normalized or not right_normalized:
        return 0.0
    return SequenceMatcher(None, left_normalized, right_normalized).ratio()


def _keyword_overlap(left: str, right: str) -> float:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _tokens(text: str) -> set[str]:
    normalized = _normalize(text)
    ascii_words = set(re.findall(r"[a-z0-9]+", normalized))
    chinese = "".join(re.findall(r"[\u3400-\u9fff]", normalized))
    chinese_tokens = {chinese[index : index + 2] for index in range(max(len(chinese) - 1, 0))}
    if len(chinese) == 1:
        chinese_tokens.add(chinese)
    return ascii_words | chinese_tokens


def _normalize(text: str) -> str:
    return "".join(re.findall(r"[a-z0-9\u3400-\u9fff]+", text.casefold()))


def _duplicate_texts(pages: list[PageExtraction]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for page in pages:
        text = _normalize(page.text)
        if text and text in seen:
            duplicates.add(text)
        seen.add(text)
    return duplicates


def _rounded(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 6)
