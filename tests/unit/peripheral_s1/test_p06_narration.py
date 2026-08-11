from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError


def test_p06_normalizes_import_assignments_and_redacts_credentials() -> None:
    from workbench.business_modules.p06_narration.runner import (
        normalize_assignments,
        safe_parameters,
    )

    page_id = uuid4()
    result = normalize_assignments(
        [{"page_id": str(page_id), "text": "  First draft  ", "author": "editor"}]
    )

    assert result == [{"page_id": str(page_id), "text": "First draft", "author": "editor"}]
    assert safe_parameters({"api_key": "secret"}) == {"api_key": "[REDACTED]"}


def test_p06_rejects_generate_context_for_another_page() -> None:
    from workbench.business_modules.p06_narration.models import NarrationGenerateParameters

    with pytest.raises(ValidationError, match="context page"):
        NarrationGenerateParameters.model_validate(
            {
                "page_id": str(uuid4()),
                "profile_id": str(uuid4()),
                "context": {
                    "page_id": str(uuid4()),
                    "page_text": "current page only",
                    "page_source_ref": "slide:1",
                },
            }
        )


def test_p06_rejects_duplicate_import_pages() -> None:
    from workbench.business_modules.p06_narration.models import NarrationImportParameters

    page_id = uuid4()
    assignment = {"page_id": str(page_id), "text": "draft"}
    with pytest.raises(ValidationError, match="duplicate pages"):
        NarrationImportParameters.model_validate({"assignments": [assignment, assignment]})
