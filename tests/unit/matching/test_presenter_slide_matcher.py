import json
from pathlib import Path
from uuid import UUID

from workbench.domain.transcript import PresenterTranscriptSentence
from workbench.matching.presenter_slide_matcher import (
    PresenterMatchPage,
    match_presenter_to_slides,
)
from workbench.matching.text_normalization import normalize_presenter_text

ROOT = Path(__file__).resolve().parents[3]


def _sentence(identifier: str, text: str, start: int) -> PresenterTranscriptSentence:
    return PresenterTranscriptSentence(
        id=identifier,
        text=text,
        normalized_text=normalize_presenter_text(text),
        start_ms=start,
        end_ms=start + 900,
    )


def test_matcher_does_not_jump_back_without_explicit_anchor() -> None:
    pages = [
        PresenterMatchPage(page_id=UUID(int=1), page_index=0, title="概览", slide_text="专业概览"),
        PresenterMatchPage(page_id=UUID(int=2), page_index=1, title="课程", slide_text="核心课程"),
    ]
    sentences = [
        _sentence("s1", "核心课程", 0),
        _sentence("s2", "专业概览", 1_000),
    ]

    result = match_presenter_to_slides(sentences, pages)

    assert [item.page_index for item in result.matches] == sorted(
        item.page_index for item in result.matches
    )
    assert "s2" in result.unassigned_sentence_ids


def test_fixture_accuracy_and_evidence_reach_baseline() -> None:
    payload = json.loads(
        (ROOT / "tests/fixtures/presenter/matching-cases.json").read_text(encoding="utf-8")
    )
    pages = [PresenterMatchPage.model_validate(item) for item in payload["pages"]]
    sentences = [
        _sentence(item["id"], item["text"], index * 1_000)
        for index, item in enumerate(payload["sentences"])
    ]

    result = match_presenter_to_slides(sentences, pages)
    expected = {item["id"]: item["expected_page_index"] for item in payload["sentences"]}
    correct = sum(expected[item.sentence_ids[0]] == item.page_index for item in result.matches)

    assert correct / len(expected) >= 0.9
    assert all(item.evidence for item in result.matches)


def test_normalization_preserves_original_meaning() -> None:
    assert normalize_presenter_text("专业组Ａ，录取率５０％") == "专业组a 录取率50%"
