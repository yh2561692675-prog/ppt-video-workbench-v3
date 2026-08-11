from __future__ import annotations

from datetime import UTC, datetime

from workbench.foundation.contracts import GateEvidenceV1


def test_gate_evidence_json_is_deterministic_for_same_payload() -> None:
    payload = GateEvidenceV1(
        schema_version="1.0",
        gate_id="G4-FOUNDATION",
        command_id="cmd-foundation",
        foundation_id="foundation-20260811-120000-abcdef1",
        snapshot_sha256="a" * 64,
        status="passed",
        started_at=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
        finished_at=datetime(2026, 8, 11, 12, 1, tzinfo=UTC),
        exit_code=0,
        tool_versions={"python": "3.12"},
        log_refs=["evidence/G4/stdout.log"],
        artifact_refs=[],
    )
    first = payload.model_dump_json(by_alias=True, exclude_none=True)
    second = payload.model_dump_json(by_alias=True, exclude_none=True)
    assert first == second
