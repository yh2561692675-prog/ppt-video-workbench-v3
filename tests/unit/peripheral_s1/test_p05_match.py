from __future__ import annotations

from uuid import uuid4


def test_p05_runner_matches_pages_and_marks_duplicates() -> None:
    from workbench.business_modules.p05_match.runner import match_payload

    page_a = uuid4()
    page_b = uuid4()
    pages = [
        {"id": str(page_a), "order": 1, "title": "概览", "text": "相同内容", "spans": [],
         "hidden": False, "rotation": 0, "needs_confirmation": False,
         "extraction_method": "pptx", "source_ref": "slide:1"},
        {"id": str(page_b), "order": 2, "title": "体系", "text": "相同内容", "spans": [],
         "hidden": False, "rotation": 0, "needs_confirmation": False,
         "extraction_method": "pptx", "source_ref": "slide:2"},
    ]
    outline = {"source_name": "outline.docx", "blocks": [
        {"kind": "heading", "order": 1, "level": 1, "text": "概览", "source_ref": "paragraph:1"},
        {"kind": "paragraph", "order": 2, "level": None, "text": "相同内容", "source_ref": "paragraph:2"},
    ]}

    matches = match_payload(outline, pages)

    assert len(matches) == 2
    assert "duplicate_page_content" in matches[1]["conflicts"]
    assert matches[0]["candidates"]
