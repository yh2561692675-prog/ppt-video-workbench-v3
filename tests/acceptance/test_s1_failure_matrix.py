from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from peripheral_contracts import ArtifactRef, JobEnvelope


def test_unknown_or_cross_module_job_types_are_rejected() -> None:
    from workbench.business_modules.registry import validate_module_job_type

    with pytest.raises(ValueError, match="not registered"):
        validate_module_job_type("P11", "delivery.archive")
    with pytest.raises(ValueError, match="unknown S1 module"):
        validate_module_job_type("P99", "video.render")


def test_delivery_without_required_human_evidence_publishes_no_archive(tmp_path: Path) -> None:
    from workbench.business_modules.p12_delivery.runner import _handle

    package = tmp_path / "package.zip"
    package.write_bytes(b"immutable package")
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    placeholder = {
        "logical_name": "quality-report-json",
        "relative_path": "08_输出/验收/quality-report.json",
        "size_bytes": 1,
        "sha256": "0" * 64,
    }
    job = JobEnvelope(
        schema_version="1.0",
        job_id=uuid4(),
        project_id=uuid4(),
        job_type="delivery.archive",
        requested_by="acceptance",
        idempotency_key=uuid4().hex,
        inputs=(
            ArtifactRef(
                artifact_id=uuid4(),
                kind="zip",
                path="package.zip",
                size_bytes=package.stat().st_size,
                sha256=digest,
            ),
        ),
        parameters={
            "project_revision": 1,
            "quality_report": {
                "automated_passed": True,
                "checks": [{"code": "automated", "passed": True}],
                "package_sha256": digest,
                "missing_evidence": ["windows", "manual_av"],
                "required_signers": ["producer", "reviewer"],
                "generated_at": datetime.now(UTC).isoformat(),
                "artifacts": [
                    placeholder,
                    {
                        **placeholder,
                        "logical_name": "quality-report-md",
                        "relative_path": "08_输出/验收/quality-report.md",
                    },
                ],
            },
        },
        created_at=datetime.now(UTC),
    )

    execution = _handle(job, tmp_path)

    assert execution.business_result.payload["decision"] == "blocked"
    assert set(execution.business_result.payload["reasons"]) == {
        "required_evidence_missing",
        "required_signature_missing",
    }
    assert execution.artifacts == ()
    assert not list(tmp_path.glob("delivery-*.zip"))
