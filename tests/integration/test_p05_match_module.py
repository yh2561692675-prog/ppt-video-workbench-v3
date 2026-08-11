from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from peripheral_contracts import BusinessResultManifest
from workbench.domain.extraction import PageExtraction
from workbench.domain.models import ProjectManifest
from workbench.domain.outline import OutlineDocument
from workbench.matching.page_matcher import match_outline_to_pages


def test_p05_projector_preserves_existing_manual_binding(tmp_path: Path) -> None:
    from workbench.business_modules.p05_match.runner import project_page_matches

    page_id = uuid4()
    outline = OutlineDocument.model_validate(
        {
            "source_name": "outline.docx",
            "blocks": [
                {
                    "kind": "heading",
                    "order": 1,
                    "level": 1,
                    "text": "Title",
                    "source_ref": "paragraph:1",
                }
            ],
        }
    )
    page = PageExtraction.model_validate(
        {
            "id": str(page_id),
            "order": 1,
            "title": "Title",
            "text": "Title",
            "spans": [],
            "hidden": False,
            "rotation": 0,
            "needs_confirmation": False,
            "extraction_method": "pptx",
            "source_ref": "slide:1",
        }
    )
    automatic = match_outline_to_pages(outline, [page]).matches[0]
    manual = automatic.model_copy(update={"decision_source": "manual"})
    project = ProjectManifest(
        id=uuid4(),
        name="demo",
        project_dir="demo",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        matches=[manual],
    )
    (tmp_path / "project.json").write_text(project.model_dump_json(), encoding="utf-8")
    incoming = automatic.model_copy(update={"score": max(0.0, automatic.score - 0.1)})
    result = BusinessResultManifest(
        schema_version="1.0",
        module_id="P05",
        job_type="content.match",
        project_id=project.id,
        project_revision=1,
        input_fingerprint="a" * 64,
        cache_key="b" * 64,
        result_type="page_matches",
        payload={
            "matches": [incoming.model_dump(mode="json")],
            "conflict_count": len(incoming.conflicts),
            "confirmation_count": int(incoming.needs_confirmation),
        },
    )

    project_page_matches(result, tmp_path)
    updated = ProjectManifest.model_validate_json(
        (tmp_path / "project.json").read_text(encoding="utf-8")
    )

    assert updated.matches[0].decision_source == "manual"
    assert updated.matches[0].selected_outline_ref == manual.selected_outline_ref
