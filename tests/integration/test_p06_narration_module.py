from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from peripheral_contracts import JobEnvelope
from workbench.business_modules.p06_narration.runner import (
    _handle,
    project_narration_revisions,
)
from workbench.domain.models import PageRecord, ProjectManifest


def _job(project_id: UUID, page_id: UUID) -> JobEnvelope:
    return JobEnvelope(
        schema_version="1.0",
        job_id=uuid4(),
        project_id=project_id,
        job_type="narration.import",
        requested_by="test",
        idempotency_key=uuid4().hex,
        parameters={
            "project_revision": 1,
            "assignments": [
                {
                    "page_id": str(page_id),
                    "expected_revision_id": None,
                    "expected_version": 0,
                    "text": "First immutable draft",
                    "author": "editor",
                    "source_refs": ["slide:1"],
                }
            ],
        },
        created_at=datetime.now(UTC),
    )


def test_p06_projects_an_immutable_revision_and_rejects_stale_expected_revision(
    tmp_path: Path,
) -> None:
    project_id = uuid4()
    page_id = uuid4()
    manifest = ProjectManifest(
        id=project_id,
        name="demo",
        project_dir="demo",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        pages=[PageRecord(id=page_id, order=1)],
    )
    (tmp_path / "project.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    execution = _handle(_job(project_id, page_id), tmp_path / "attempt")

    project_narration_revisions(execution.business_result, tmp_path)

    updated = ProjectManifest.model_validate_json(
        (tmp_path / "project.json").read_text(encoding="utf-8")
    )
    revision = updated.pages[0].narration
    assert revision is not None
    assert revision.version == 1
    assert revision.confirmed_revision_id is None
    history = tmp_path / "04_旁白" / "历史版本" / str(page_id) / f"{revision.id}.json"
    assert history.is_file()
    before = history.read_bytes()

    with pytest.raises(ValueError, match="NARRATION_REVISION_CONFLICT"):
        project_narration_revisions(execution.business_result, tmp_path)
    assert history.read_bytes() == before


def test_p06_exports_only_explicitly_confirmed_pages(tmp_path: Path) -> None:
    job = JobEnvelope(
        schema_version="1.0",
        job_id=uuid4(),
        project_id=uuid4(),
        job_type="narration.export",
        requested_by="test",
        idempotency_key=uuid4().hex,
        parameters={
            "project_revision": 1,
            "project_name": "demo",
            "pages": [
                {
                    "page_id": str(uuid4()),
                    "page_order": 1,
                    "revision_id": str(uuid4()),
                    "version": 1,
                    "text": "Confirmed narration",
                    "confirmed": True,
                    "confirmed_by": "reviewer",
                    "confirmed_at": datetime.now(UTC).isoformat(),
                }
            ],
        },
        created_at=datetime.now(UTC),
    )

    execution = _handle(job, tmp_path)

    assert execution.business_result.result_type == "narration_docx"
    assert execution.business_result.payload["page_count"] == 1
    assert execution.artifacts[0].path.read_bytes().startswith(b"PK")
