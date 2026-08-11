from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from workbench.foundation.contracts import (
    FoundationFreezeManifestV1,
    GateEvidenceV1,
    OwnershipMapV1,
    WindowStopPointV1,
)

ROOT = Path(__file__).parents[2]
SHA = "a" * 64
HEAD = "b" * 40


def _repository() -> dict[str, str]:
    return {
        "path": "source-root",
        "branch": "recovery/root-snapshot-20260810",
        "head": HEAD,
        "status_manifest_sha256": SHA,
    }


def test_schema_files_are_strict_and_have_expected_titles() -> None:
    expected = {
        "window-stop-point-v1.schema.json": "WindowStopPointV1",
        "ownership-map-v1.schema.json": "OwnershipMapV1",
        "foundation-freeze-manifest-v1.schema.json": "FoundationFreezeManifestV1",
        "gate-evidence-v1.schema.json": "GateEvidenceV1",
    }
    for filename, title in expected.items():
        schema = json.loads(
            (ROOT / "schemas" / "foundation" / filename).read_text(encoding="utf-8")
        )
        assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert schema["title"] == title
        assert schema["additionalProperties"] is False


def test_stop_point_accepts_logical_paths_and_rejects_escape() -> None:
    point = WindowStopPointV1(
        schema_version="1.0",
        window_id="window-foundation",
        task_name="shared foundation",
        mode="idle",
        repository=_repository(),
        owned_paths=["docs/acceptance/foundation"],
        shared_paths_touched=["apps/api/src/workbench/main.py"],
        completed=["inventory"],
        remaining=[],
        evidence_refs=["evidence/inventory.json"],
        will_write_again=False,
        safe_resume="Read the checkpoint manifest before continuing.",
    )
    assert point.owned_paths == ["docs/acceptance/foundation"]

    with pytest.raises(ValidationError):
        invalid_payload = point.model_dump()
        invalid_payload["owned_paths"] = ["../outside"]
        WindowStopPointV1(**invalid_payload)


def test_ownership_map_requires_hash_and_forbids_unknown_fields() -> None:
    payload = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC),
        "entries": [
            {
                "path": "apps/api/src/workbench/foundation/contracts.py",
                "owner_window_id": "window-foundation",
                "category": "source",
                "authority": True,
            }
        ],
        "unknown_paths": [],
        "semantic_conflicts": [],
        "source_status_manifest_sha256": SHA,
    }
    assert OwnershipMapV1.model_validate(payload).entries[0].authority is True
    with pytest.raises(ValidationError):
        OwnershipMapV1.model_validate({**payload, "unexpected": True})
    with pytest.raises(ValidationError):
        OwnershipMapV1.model_validate({**payload, "source_status_manifest_sha256": "bad"})


def test_freeze_manifest_and_gate_evidence_share_the_snapshot_hash() -> None:
    manifest = FoundationFreezeManifestV1(
        schema_version="1.0",
        foundation_id="foundation-20260811-120000-abcdef1",
        created_at=datetime.now(UTC),
        repository=_repository(),
        checkpoint_ref="refs/foundation/foundation-20260811-120000-abcdef1",
        snapshot_sha256=SHA,
        stop_point_ids=["window-foundation"],
        ownership_map_sha256=SHA,
        conflict_resolution_sha256=SHA,
        boundaries=[
            {
                "boundary_id": boundary,
                "logical_root": f"{boundary}-root",
                "exists": True,
                "writable": False,
                "containment_verified": True,
            }
            for boundary in ("source", "installed", "workspace_data", "video")
        ],
        includes=["apps/api/src/workbench/foundation"],
        excludes=[".tmp"],
        dependency_lock_sha256=SHA,
        gate_evidence_refs=["evidence/G0.json"],
        release_level="candidate",
    )
    evidence = GateEvidenceV1(
        schema_version="1.0",
        gate_id="G0-BOUNDARY",
        command_id="cmd-boundary",
        foundation_id=manifest.foundation_id,
        snapshot_sha256=manifest.snapshot_sha256,
        status="passed",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        exit_code=0,
        log_refs=["evidence/G0/stdout.log"],
        artifact_refs=[],
    )
    assert evidence.snapshot_sha256 == manifest.snapshot_sha256


def test_gate_evidence_rejects_invalid_gate_and_absolute_refs() -> None:
    with pytest.raises(ValidationError):
        GateEvidenceV1(
            schema_version="1.0",
            gate_id="G9",
            command_id="cmd",
            foundation_id="foundation-test",
            snapshot_sha256=SHA,
            status="passed",
            started_at=datetime.now(UTC),
            finished_at=datetime.now(UTC),
            log_refs=["F:/secret.log"],
            artifact_refs=[],
        )
