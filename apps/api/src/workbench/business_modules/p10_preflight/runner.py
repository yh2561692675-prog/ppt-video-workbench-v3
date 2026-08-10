from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from peripheral_contracts import BusinessResultManifest, JobEnvelope

from workbench.business_modules.runtime import (
    BusinessExecution,
    StagedArtifact,
    business_input_fingerprint,
    execute_business_handler,
)
from workbench.domain.models import AuditEvent, ProjectManifest
from workbench.preflight.engine import PreflightEngine


def run_preflight(project: ProjectManifest, workspace_root: Path) -> dict[str, Any]:
    report = PreflightEngine(workspace_root).run_preflight(project)
    return report.model_dump(mode="json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    job = JobEnvelope.model_validate_json(args.request.read_text(encoding="utf-8"))

    def handler(received: JobEnvelope, attempt_root: Path) -> BusinessExecution:
        manifest_payload = received.parameters.get("project_manifest")
        if not isinstance(manifest_payload, dict):
            raise ValueError("parameters.project_manifest is required")
        project = ProjectManifest.model_validate(manifest_payload)
        report = run_preflight(project, attempt_root)
        output = attempt_root / "preflight.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fingerprint = business_input_fingerprint(received)
        result = BusinessResultManifest(
            schema_version="1.0",
            module_id="P10",
            job_type=received.job_type,
            project_id=received.project_id,
            project_revision=int(received.parameters.get("project_revision", 1)),
            input_fingerprint=fingerprint,
            cache_key=hashlib.sha256((fingerprint + "preflight_report").encode()).hexdigest(),
            result_type="preflight_report",
            payload=report,
        )
        return BusinessExecution(result, (StagedArtifact("preflight", "json", output),))

    execution = execute_business_handler(job, args.result.parent, args.result, "P10", handler)
    return 0 if execution.outcome == "succeeded" else 1


def project_preflight_report(result: BusinessResultManifest, project_dir: Path) -> None:
    manifest_path = project_dir / "project.json"
    manifest = ProjectManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    from workbench.domain.issues import PreflightReport

    report = PreflightReport.model_validate(result.payload)
    updated = manifest.model_copy(
        update={
            "preflight_report": report,
            "preflight_history": [*manifest.preflight_history, report.input_fingerprint],
            "audit_log": [
                *manifest.audit_log,
                AuditEvent(
                    action="preflight_completed",
                    occurred_at=datetime.now(UTC),
                    details={"allowed": report.allowed, "issue_count": len(report.issues)},
                ),
            ],
        }
    )
    temporary = manifest_path.with_name(".project.json.s1.tmp")
    temporary.write_text(updated.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(manifest_path)


if __name__ == "__main__":
    raise SystemExit(main())
