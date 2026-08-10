from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from peripheral_contracts import BusinessResultManifest
from workbench.domain.models import ProjectManifest


def test_p03_projector_updates_project_manifest_and_audit(tmp_path: Path) -> None:
    from workbench.business_modules.p03_material.runner import project_material_sources

    project = ProjectManifest(
        id=uuid4(),
        name="demo",
        project_dir="demo",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    project_path = tmp_path / "project.json"
    project_path.write_text(project.model_dump_json(), encoding="utf-8")
    result = BusinessResultManifest(
        schema_version="1.0",
        module_id="P03",
        job_type="material.ingest",
        project_id=project.id,
        project_revision=1,
        input_fingerprint="a" * 64,
        cache_key="b" * 64,
        result_type="material_sources",
        payload={
            "operation": "ingest",
            "sources": [
                {
                    "original_name": "slides.pdf",
                    "safe_name": "slides.pdf",
                    "kind": "pdf",
                    "size_bytes": 32,
                    "sha256": "c" * 64,
                    "relative_path": "slides.pdf",
                }
            ],
            "ordered_names": ["slides.pdf"],
        },
    )

    project_material_sources(result, tmp_path)
    updated = ProjectManifest.model_validate_json(project_path.read_text(encoding="utf-8"))

    assert updated.source_files[0].safe_name == "slides.pdf"
    assert updated.audit_log[-1].action == "sources_imported"
