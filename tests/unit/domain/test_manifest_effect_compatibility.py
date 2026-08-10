from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from workbench.domain.models import PageRecord, ProjectManifest, validate_manifest


def test_legacy_manifest_without_effect_fields_loads_with_defaults() -> None:
    project_id = uuid4()
    payload = {
        "schema_version": 1,
        "id": str(project_id),
        "name": "legacy",
        "project_dir": "legacy",
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
        "pages": [{"id": str(uuid4()), "order": 1}],
    }

    manifest = validate_manifest(payload)

    assert manifest.effect_policy.aspect_ratio == "16:9"
    assert manifest.pages[0].effect_plan is None
