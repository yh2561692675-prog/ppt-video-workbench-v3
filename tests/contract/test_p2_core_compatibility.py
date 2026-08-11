from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from workbench.contracts.core_compat import (
    CORE_CONTRACT_SET_SHA256,
    CoreCompatibilityEnvelopeV1,
    project_p2_error,
)
from workbench.contracts.p2_platform import BudgetV1

from cloud_prototype.app import JobCreate

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "packages" / "contracts" / "p2-platform" / "core-compatibility.json"


def _manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_p2_and_core_version_namespaces_are_explicitly_separate() -> None:
    manifest = _manifest()
    boundary = manifest["namespace_boundary"]
    assert boundary == {
        "p2_cloud_envelope_major": 1,
        "core_wire_versions_are_independent": True,
        "implicit_version_conversion": False,
    }
    assert manifest["core_contract_set_sha256"] == CORE_CONTRACT_SET_SHA256
    assert manifest["core_versions"] == {
        "project": 1,
        "asset": "1.0",
        "material": "1.0",
        "timeline": "1.0",
        "subtitle": 2,
        "continuity": 1,
        "render_graph": "2.0",
        "job": "1.0",
        "export": "1.0",
        "quality": "1.0",
    }


def test_remote_job_pins_a13_job_asset_and_error_contracts() -> None:
    job = JobCreate(
        revision_id=uuid4(),
        kind="render",
        provider_policy_sha256="sha256:" + "1" * 64,
        provider_budget=BudgetV1(timeout_ms=1_000, max_cost_minor=0),
        provider_cost_estimate_minor=0,
        runtime_image_sha256="sha256:" + "2" * 64,
        fingerprints={
            "provider_policy": "sha256:" + "1" * 64,
            "runtime": "sha256:" + "2" * 64,
            "platform": "sha256:" + "3" * 64,
            "input": "sha256:" + "4" * 64,
        },
    )
    assert job.core_contracts == CoreCompatibilityEnvelopeV1()
    assert job.core_contracts.job_schema_version == "1.0"
    assert job.core_contracts.asset_schema_version == "1.0"
    assert job.core_contracts.version_conversion == "none"
    with pytest.raises(ValidationError):
        JobCreate.model_validate(
            {
                **job.model_dump(mode="json"),
                "core_contracts": {
                    **job.core_contracts.model_dump(mode="json"),
                    "job_schema_version": 1,
                },
            }
        )


def test_unknown_error_code_fails_closed_in_core_projection() -> None:
    known = project_p2_error(code="provider.timeout", message="timed out")
    assert known.code == "P2_PROVIDER_FAILURE"
    assert known.blocking is True
    unknown = project_p2_error(code="provider.future_behavior", message="future")
    assert unknown.code == "P2_UNMAPPED_ERROR"
    assert unknown.blocking is True
    assert "before retrying" in unknown.action


def test_compatibility_policy_matches_a13_and_optional_catalog() -> None:
    manifest = _manifest()
    assert manifest["compatibility"] == {
        "unknown_fields": "reject",
        "older_versions": "explicit_migration",
        "invalid_enum": "reject",
    }
    catalog_path = ROOT / "packages" / "contracts" / "v1-contract-catalog.json"
    if catalog_path.exists():
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        assert catalog["contract_set_sha256"] == manifest["core_contract_set_sha256"]


def test_openapi_and_typescript_publish_the_same_core_envelope() -> None:
    openapi = (ROOT / "schemas" / "cloud" / "cloud-collaboration-v1.openapi.yaml").read_text(
        encoding="utf-8"
    )
    typescript = (ROOT / "packages" / "contracts" / "p2-platform" / "index.ts").read_text(
        encoding="utf-8"
    )
    assert "CoreContractCompatibility:" in openapi
    assert "core_contracts:" in openapi
    assert CORE_CONTRACT_SET_SHA256 in openapi
    assert "interface CoreContractCompatibilityV1" in typescript
    assert CORE_CONTRACT_SET_SHA256 in typescript


def test_canonical_fingerprint_migration_updates_existing_remote_jobs(
    tmp_path: Path,
) -> None:
    old_hash = "7c63aab737d6fe9281ce83cd8fec0e2ddf52f2148d51938f6be4f80ac55f5488"
    database = tmp_path / "compatibility.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE jobs (core_contracts_json TEXT NOT NULL)")
        connection.execute(
            "INSERT INTO jobs (core_contracts_json) VALUES (?)",
            (json.dumps({"core_contract_set_sha256": old_hash}),),
        )
        migration = (
            ROOT
            / "cloud_prototype"
            / "migrations"
            / "0008_core_contract_canonical_fingerprint.sql"
        ).read_text(encoding="utf-8")
        connection.executescript(migration)
        stored = connection.execute("SELECT core_contracts_json FROM jobs").fetchone()
    assert stored is not None
    assert json.loads(stored[0])["core_contract_set_sha256"] == CORE_CONTRACT_SET_SHA256
