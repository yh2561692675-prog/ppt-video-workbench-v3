from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from workbench.quality.models import QualityIssue, QualityReport, QualityScope, QualitySeverity


def test_quality_contract_schemas_are_valid_json_and_match_model_shape() -> None:
    report_schema = json.loads(
        Path("schemas/quality-report-v1.schema.json").read_text(encoding="utf-8")
    )
    policy_schema = json.loads(
        Path("schemas/quality-policy-v1.schema.json").read_text(encoding="utf-8")
    )
    assert report_schema["title"] == "QualityReportV1"
    assert policy_schema["title"] == "QualityPolicyV1"

    issue = QualityIssue(
        code="audio_silence",
        severity=QualitySeverity.P2,
        scope=QualityScope.TIME_RANGE,
        start_ms=1,
        end_ms=2,
        message="silence",
        action="review",
    )
    report = QualityReport(
        project_id=uuid4(),
        render_job_id=uuid4(),
        report_id=uuid4(),
        input_fingerprint="0" * 64,
        result="pass_with_warnings",
        issues=[issue],
    )
    assert report.model_dump(mode="json")["issues"][0]["issue_id"]
