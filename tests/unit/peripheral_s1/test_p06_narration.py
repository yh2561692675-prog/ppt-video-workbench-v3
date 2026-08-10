from __future__ import annotations

from uuid import uuid4


def test_p06_normalizes_import_assignments_and_redacts_credentials() -> None:
    from workbench.business_modules.p06_narration.runner import normalize_assignments

    page_id = uuid4()
    result = normalize_assignments([
        {"page_id": str(page_id), "text": "  第一页旁白  ", "author": "editor"},
    ])

    assert result == [{"page_id": str(page_id), "text": "第一页旁白", "author": "editor"}]
