import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from workbench.domain.models import (
    ProjectManifest,
    migrate_manifest,
    stable_page_id,
    validate_manifest,
)
from workbench.main import create_app

ROOT = Path(__file__).resolve().parents[2]


def minimum_project_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "id": str(uuid4()),
        "name": "计算机类专业介绍",
        "project_dir": "计算机类专业介绍_20260803_1630",
        "created_at": "2026-08-03T16:30:00+08:00",
        "updated_at": "2026-08-03T16:30:00+08:00",
        "current_step": 1,
        "status": "not_started",
        "pages": [],
        "jobs": [],
    }


def test_minimum_project_manifest_is_valid() -> None:
    manifest = validate_manifest(minimum_project_payload())

    assert isinstance(manifest, ProjectManifest)
    assert manifest.name == "计算机类专业介绍"
    assert manifest.schema_version == 1


def test_unknown_node_status_is_rejected() -> None:
    payload = minimum_project_payload()
    payload["status"] = "done"

    with pytest.raises(ValidationError):
        validate_manifest(payload)


def test_page_without_id_is_rejected() -> None:
    payload = minimum_project_payload()
    payload["pages"] = [{"order": 1, "status": "not_started"}]

    with pytest.raises(ValidationError, match="id"):
        validate_manifest(payload)


def test_duplicate_page_order_is_rejected() -> None:
    payload = minimum_project_payload()
    payload["pages"] = [
        {"id": str(uuid4()), "order": 1, "status": "not_started"},
        {"id": str(uuid4()), "order": 1, "status": "not_started"},
    ]

    with pytest.raises(ValidationError, match="page order"):
        validate_manifest(payload)


def test_page_ids_are_stable_within_a_project() -> None:
    project_id = uuid4()

    first = stable_page_id(project_id, 1)

    assert isinstance(first, UUID)
    assert first == stable_page_id(project_id, 1)
    assert first != stable_page_id(project_id, 2)


def test_schema_version_zero_requires_explicit_migration() -> None:
    legacy = {
        "schema_version": 0,
        "id": str(uuid4()),
        "project_name": "旧项目",
        "path": "旧项目_20260701_0900",
        "created_at": "2026-07-01T09:00:00+08:00",
        "pages": [],
    }

    with pytest.raises(ValidationError):
        validate_manifest(legacy)

    migrated = migrate_manifest(legacy, target_version=1)
    manifest = validate_manifest(migrated)

    assert manifest.schema_version == 1
    assert manifest.name == "旧项目"
    assert manifest.project_dir == "旧项目_20260701_0900"


def test_generated_json_schema_matches_committed_contract() -> None:
    committed = json.loads((ROOT / "packages/contracts/project.schema.json").read_text("utf-8"))

    assert committed == ProjectManifest.model_json_schema()


def test_openapi_snapshot_matches_application_contract() -> None:
    committed = json.loads((ROOT / "packages/contracts/openapi.json").read_text("utf-8"))

    assert committed == create_app().openapi()


def test_openapi_exposes_typed_project_response_contract() -> None:
    schema = create_app().openapi()

    assert "ProjectManifest" in schema["components"]["schemas"]
    response_schema = schema["paths"]["/api/projects/{project_id}"]["get"]["responses"]["200"]
    serialized = json.dumps(response_schema, ensure_ascii=False)
    assert "ProjectManifest" in serialized
