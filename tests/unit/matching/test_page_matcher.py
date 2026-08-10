from __future__ import annotations

from uuid import NAMESPACE_URL, uuid4, uuid5

from workbench.domain.extraction import PageExtraction
from workbench.domain.outline import OutlineBlock, OutlineDocument
from workbench.matching.page_matcher import match_outline_to_pages


def outline() -> OutlineDocument:
    return OutlineDocument(
        source_name="大纲.docx",
        blocks=[
            OutlineBlock(
                kind="heading", order=1, level=1, text="专业概览", source_ref="paragraph:1"
            ),
            OutlineBlock(
                kind="paragraph", order=2, text="培养目标与专业特点", source_ref="paragraph:2"
            ),
            OutlineBlock(
                kind="heading", order=3, level=1, text="课程体系", source_ref="paragraph:3"
            ),
            OutlineBlock(
                kind="paragraph", order=4, text="高等数学与机器学习", source_ref="paragraph:4"
            ),
            OutlineBlock(
                kind="heading", order=5, level=1, text="就业方向", source_ref="paragraph:5"
            ),
            OutlineBlock(
                kind="paragraph", order=6, text="算法工程师与研发岗位", source_ref="paragraph:6"
            ),
        ],
    )


def page(order: int, title: str, body: str) -> PageExtraction:
    return PageExtraction(
        id=uuid5(NAMESPACE_URL, f"page:{order}:{title}:{body}"),
        order=order,
        title=title or None,
        text="\n".join(value for value in [title, body] if value),
        extraction_method="pptx",
        source_ref=f"slide:{order}",
    )


def test_matching_uses_explainable_fixed_weights_and_content_can_beat_order() -> None:
    pages = [
        page(1, "课程体系", "高等数学与机器学习"),
        page(2, "专业概览", "培养目标与专业特点"),
        page(3, "就业方向", "算法工程师与研发岗位"),
    ]

    plan = match_outline_to_pages(outline(), pages)

    assert [match.selected_outline_ref for match in plan.matches] == [
        "paragraph:3",
        "paragraph:1",
        "paragraph:5",
    ]
    first = plan.matches[0].candidates[0]
    assert first.weights.model_dump() == {
        "page_order": 0.20,
        "title": 0.45,
        "keywords": 0.25,
        "body": 0.10,
    }
    assert first.components.title == 1.0
    assert first.score >= 0.75


def test_empty_duplicate_and_contradictory_pages_require_confirmation() -> None:
    duplicate = page(1, "专业概览", "培养目标与专业特点")
    pages = [
        duplicate,
        duplicate.model_copy(update={"id": uuid4(), "order": 2}),
        page(3, "完全无关标题", "火星地质样本"),
        page(4, "", ""),
    ]

    plan = match_outline_to_pages(outline(), pages)

    assert "duplicate_page_content" in plan.matches[0].conflicts
    assert "duplicate_page_content" in plan.matches[1].conflicts
    assert plan.matches[2].needs_confirmation is True
    assert "title_conflict" in plan.matches[2].conflicts
    assert plan.matches[3].needs_confirmation is True
    assert "empty_page" in plan.matches[3].conflicts
    assert all(match.decision_source == "deterministic_rules" for match in plan.matches)


def test_eight_page_sample_keeps_one_to_one_title_matches() -> None:
    sample_outline = OutlineDocument(
        source_name="八页大纲.docx",
        blocks=[
            OutlineBlock(
                kind="heading",
                order=index,
                level=1,
                text=f"主题{index}",
                source_ref=f"paragraph:{index}",
            )
            for index in range(1, 9)
        ],
    )
    pages = [page(index, f"主题{index}", "") for index in range(1, 9)]

    plan = match_outline_to_pages(sample_outline, pages)

    assert [match.selected_outline_ref for match in plan.matches] == [
        f"paragraph:{index}" for index in range(1, 9)
    ]
