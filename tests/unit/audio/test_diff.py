from __future__ import annotations

from uuid import uuid4

import pytest
from workbench.audio.diff import NarrationText, compare
from workbench.audio.models import Transcript, TranscriptSegment, TranscriptWord


def _transcript(text: str, confidence: float = 0.99) -> Transcript:
    word = TranscriptWord(text=text, start_ms=100, end_ms=900, confidence=confidence)
    return Transcript(
        segments=[TranscriptSegment(text=text, start_ms=100, end_ms=900, words=[word])],
        words=[word],
        detected_language="zh",
        model="small",
        device="cpu",
    )


def _narration(text: str) -> NarrationText:
    return NarrationText(page_id=uuid4(), text=text)


@pytest.mark.parametrize(
    ("expected", "spoken"),
    [
        ("你好，世界！", "你好世界"),
        ("2026年招生", "二零二六年招生"),
        ("AI专业", "ai 专业"),
        ("A.I.技术", "AI技术"),
    ],
)
def test_normalizes_punctuation_digits_and_abbreviations(expected: str, spoken: str) -> None:
    assert compare(_transcript(spoken), [_narration(expected)]) == []


@pytest.mark.parametrize(
    ("expected", "spoken", "kind"),
    [
        ("这是完整旁白", "这是旁白", "omission"),
        ("这是旁白", "这是额外完整旁白", "addition"),
        ("培养目标明确", "培养方向明确", "misread"),
    ],
)
def test_classifies_blocking_differences(expected: str, spoken: str, kind: str) -> None:
    differences = compare(_transcript(spoken), [_narration(expected)])
    assert kind in {item.kind for item in differences}
    assert all(item.status == "pending" for item in differences)
    assert all(item.start_ms <= item.end_ms for item in differences)


def test_low_confidence_equal_word_is_uncertain() -> None:
    differences = compare(_transcript("专有名词", 0.2), [_narration("专有名词")])
    assert [item.kind for item in differences] == ["uncertain"]
    assert differences[0].confidence == 0.2


def test_thirty_labeled_blocking_pairs_reach_recall_target() -> None:
    labels = [(f"第{index}页介绍培养目标", f"第{index}页介绍就业目标") for index in range(1, 31)]
    detected = sum(
        bool(compare(_transcript(spoken), [_narration(expected)])) for expected, spoken in labels
    )
    assert detected / len(labels) >= 0.95
