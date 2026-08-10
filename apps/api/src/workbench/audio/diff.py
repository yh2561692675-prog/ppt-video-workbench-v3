from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal
from uuid import UUID, uuid4

from workbench.audio.models import Transcript
from workbench.domain.audio import AudioDifference

_DIGITS = str.maketrans("0123456789", "零一二三四五六七八九")
_TOKEN = re.compile(r"[a-z]+|[\u4e00-\u9fff]")


@dataclass(frozen=True)
class NarrationText:
    page_id: UUID
    text: str


@dataclass(frozen=True)
class _Token:
    text: str
    page_id: UUID | None
    start_ms: int
    end_ms: int
    confidence: float


def compare(transcript: Transcript, narrations: list[NarrationText]) -> list[AudioDifference]:
    expected = [
        _Token(token, narration.page_id, 0, 0, 1.0)
        for narration in narrations
        for token in _tokens(narration.text)
    ]
    actual = [
        _Token(token, None, word.start_ms, word.end_ms, word.confidence)
        for word in transcript.words
        for token in _tokens(word.text)
    ]
    matcher = SequenceMatcher(
        None,
        [item.text for item in expected],
        [item.text for item in actual],
        autojunk=False,
    )
    differences: list[AudioDifference] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        expected_slice = expected[i1:i2]
        actual_slice = actual[j1:j2]
        page_id = _page_id(expected, expected_slice, i1, narrations)
        start_ms, end_ms, confidence = _time(actual, actual_slice, j1)
        kind: Literal["omission", "addition", "misread"]
        if tag == "delete":
            kind = "omission"
        elif tag == "insert":
            kind = "addition"
        else:
            kind = "misread"
        differences.append(
            AudioDifference(
                id=uuid4(),
                page_id=page_id,
                kind=kind,
                expected="".join(item.text for item in expected_slice),
                actual="".join(item.text for item in actual_slice),
                start_ms=start_ms,
                end_ms=end_ms,
                confidence=confidence,
            )
        )
    for word in transcript.words:
        if word.confidence < 0.55:
            differences.append(
                AudioDifference(
                    id=uuid4(),
                    page_id=_page_for_time(expected, actual, word.start_ms, narrations),
                    kind="uncertain",
                    expected=word.text,
                    actual=word.text,
                    start_ms=word.start_ms,
                    end_ms=word.end_ms,
                    confidence=word.confidence,
                )
            )
    return sorted(differences, key=lambda item: (item.start_ms, item.kind))


def _tokens(value: str) -> list[str]:
    normalized = value.translate(_DIGITS).casefold()
    normalized = re.sub(r"(?<=[a-z])\.(?=[a-z])", "", normalized)
    return _TOKEN.findall(normalized)


def _page_id(
    expected: list[_Token],
    selected: list[_Token],
    index: int,
    narrations: list[NarrationText],
) -> UUID:
    if selected and selected[0].page_id is not None:
        return selected[0].page_id
    if expected:
        nearby = expected[min(index, len(expected) - 1)].page_id
        if nearby is not None:
            return nearby
    if not narrations:
        raise ValueError("至少需要一页已确认旁白")
    return narrations[0].page_id


def _time(actual: list[_Token], selected: list[_Token], index: int) -> tuple[int, int, float]:
    if selected:
        return selected[0].start_ms, selected[-1].end_ms, min(x.confidence for x in selected)
    if actual:
        nearby = actual[min(index, len(actual) - 1)]
        return nearby.start_ms, nearby.start_ms, nearby.confidence
    return 0, 0, 0.0


def _page_for_time(
    expected: list[_Token],
    actual: list[_Token],
    time_ms: int,
    narrations: list[NarrationText],
) -> UUID:
    if not narrations:
        raise ValueError("至少需要一页已确认旁白")
    if not actual or not expected:
        return narrations[0].page_id
    closest = min(range(len(actual)), key=lambda index: abs(actual[index].start_ms - time_ms))
    ratio = closest / max(1, len(actual) - 1)
    expected_index = min(len(expected) - 1, round(ratio * (len(expected) - 1)))
    return expected[expected_index].page_id or narrations[0].page_id
