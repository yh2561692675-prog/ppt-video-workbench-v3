from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from peripheral_contracts import BusinessResultManifest
from workbench.domain.models import ProjectManifest


def test_p04_projector_updates_pages_and_extractions(tmp_path: Path) -> None:
    from workbench.business_modules.p04_extract.runner import project_document_extraction

    project = ProjectManifest(
        id=uuid4(),
        name="demo",
        project_dir="demo",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    (tmp_path / "project.json").write_text(project.model_dump_json(), encoding="utf-8")
    page_id = uuid4()
    result = BusinessResultManifest(
        schema_version="1.0",
        module_id="P04",
        job_type="document.extract",
        project_id=project.id,
        project_revision=1,
        input_fingerprint="a" * 64,
        cache_key="b" * 64,
        result_type="document_extraction",
        payload={
            "operation": "extract",
            "documents": [
                {
                    "source_name": "demo.pptx",
                    "page_count": 1,
                    "cache_key": "d" * 64,
                    "outline": {"source_name": "demo.pptx", "blocks": []},
                    "pages": [
                        {
                            "id": str(page_id),
                            "order": 1,
                            "text": "hello",
                            "title": "Title",
                            "spans": [],
                            "hidden": False,
                            "rotation": 0,
                            "needs_confirmation": False,
                            "extraction_method": "pptx",
                            "source_ref": "slide:1",
                        }
                    ],
                }
            ],
            "previews": [],
            "page_count": 1,
        },
    )

    project_document_extraction(result, tmp_path)
    updated = ProjectManifest.model_validate_json(
        (tmp_path / "project.json").read_text(encoding="utf-8")
    )

    assert updated.pages[0].title == "Title"
    assert updated.page_extractions[0].text == "hello"
    assert updated.audit_log[-1].action == "document_extraction_updated"
