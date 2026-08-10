from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from peripheral_contracts import BusinessResultManifest, JobEnvelope

from workbench.business_modules.runtime import (
    BusinessExecution,
    StagedArtifact,
    business_input_fingerprint,
    execute_business_handler,
)


def evaluate_delivery(inputs: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if inputs.get("preflight_allowed") is not True:
        reasons.append("preflight_blocked")
    if inputs.get("rendered") is not True:
        reasons.append("render_missing")
    artifacts = inputs.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        reasons.append("artifacts_missing")
    return {
        "decision": "deliverable" if not reasons else "blocked",
        "reasons": reasons,
        "artifact_count": len(artifacts) if isinstance(artifacts, list) else 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    job = JobEnvelope.model_validate_json(args.request.read_text(encoding="utf-8"))

    def handler(received: JobEnvelope, attempt_root: Path) -> BusinessExecution:
        inputs = {
            key: value
            for key, value in received.parameters.items()
            if key
            not in {
                "module_id",
                "project_revision",
                "runtime_version",
                "affected_page_ids",
                "input_fingerprint",
                "project_snapshot_sha256",
            }
        }
        decision = evaluate_delivery(inputs)
        output = attempt_root / "delivery.json"
        output.write_text(
            json.dumps(decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        fingerprint = business_input_fingerprint(received)
        result_type = (
            "quality_report" if received.job_type == "quality.verify" else "delivery_decision"
        )
        result = BusinessResultManifest(
            schema_version="1.0",
            module_id="P12",
            job_type=received.job_type,
            project_id=received.project_id,
            project_revision=int(received.parameters.get("project_revision", 1)),
            input_fingerprint=fingerprint,
            cache_key=hashlib.sha256((fingerprint + result_type).encode()).hexdigest(),
            result_type=result_type,
            payload=decision,
        )
        return BusinessExecution(result, (StagedArtifact("delivery", "json", output),))

    execution = execute_business_handler(job, args.result.parent, args.result, "P12", handler)
    return 0 if execution.outcome == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
