from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from peripheral_contracts import JobEnvelope
from workbench.business_modules.p09_effects.runner import _handle, project_effect_plan
from workbench.domain.models import PageRecord, ProjectManifest


def test_p09_projects_validated_effect_plan_without_mutating_upstream_state(
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
        pages=[PageRecord(id=page_id, order=1, title="Metric")],
    )
    (tmp_path / "project.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    job = JobEnvelope(
        schema_version="1.0",
        job_id=uuid4(),
        project_id=project_id,
        job_type="effect.plan",
        requested_by="test",
        idempotency_key=uuid4().hex,
        parameters={
            "project_revision": 1,
            "page_id": str(page_id),
            "duration_ms": 3000,
            "title": "Metric 42",
            "text": "42",
        },
        created_at=datetime.now(UTC),
    )

    execution = _handle(job, tmp_path)
    project_effect_plan(execution.business_result, tmp_path)

    updated = ProjectManifest.model_validate_json(
        (tmp_path / "project.json").read_text(encoding="utf-8")
    )
    assert updated.pages[0].effect_plan is not None
    assert updated.pages[0].effect_plan.plan.template == "StatCounter"
    assert updated.subtitle_artifact == manifest.subtitle_artifact
    assert updated.audio_import == manifest.audio_import
