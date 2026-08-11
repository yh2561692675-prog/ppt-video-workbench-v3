from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from peripheral_contracts import JobEnvelope
from workbench.business_modules.p10_preflight.runner import (
    _handle,
    project_preflight_report,
)
from workbench.domain.models import ProjectManifest


def test_p10_emits_json_and_markdown_and_projects_blocking_report(tmp_path: Path) -> None:
    project_id = uuid4()
    manifest = ProjectManifest(
        id=project_id,
        name="demo",
        project_dir="snapshot",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    (tmp_path / "project.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    job = JobEnvelope(
        schema_version="1.0",
        job_id=uuid4(),
        project_id=project_id,
        job_type="preflight.run",
        requested_by="test",
        idempotency_key=uuid4().hex,
        parameters={
            "project_revision": 1,
            "project_manifest": manifest.model_dump(mode="json"),
            "scope": ["materials", "content"],
        },
        created_at=datetime.now(UTC),
    )

    execution = _handle(job, tmp_path / "attempt")
    project_preflight_report(execution.business_result, tmp_path)

    updated = ProjectManifest.model_validate_json(
        (tmp_path / "project.json").read_text(encoding="utf-8")
    )
    assert updated.preflight_report is not None
    assert updated.preflight_report.allowed is False
    assert len(execution.artifacts) == 2
    markdown = next(item.path for item in execution.artifacts if item.kind == "markdown")
    assert "# Preflight Report" in markdown.read_text(encoding="utf-8")
