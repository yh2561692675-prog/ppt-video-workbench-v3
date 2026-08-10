from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from peripheral_contracts import BusinessResultManifest, JobEnvelope

from workbench.business_modules.runtime import (
    BusinessExecution,
    StagedArtifact,
    business_input_fingerprint,
    execute_business_handler,
)
from workbench.domain.models import AuditEvent, EffectPlanRecord, ProjectManifest
from workbench.effects.planner import EffectPlanner, EffectPlanningInput


def plan_effect(parameters: dict[str, Any]) -> dict[str, Any]:
    value = EffectPlanningInput.model_validate(parameters)
    return EffectPlanner().plan(value).model_dump(mode="json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    job = JobEnvelope.model_validate_json(args.request.read_text(encoding="utf-8"))

    def handler(received: JobEnvelope, attempt_root: Path) -> BusinessExecution:
        parameters = {
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
        plan = plan_effect(parameters)
        output = attempt_root / "effects.json"
        output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        fingerprint = business_input_fingerprint(received)
        result_type = (
            "effect_plan_v2" if received.job_type == "effect.plan" else "project_video_props"
        )
        result = BusinessResultManifest(
            schema_version="1.0",
            module_id="P09",
            job_type=received.job_type,
            project_id=received.project_id,
            project_revision=int(received.parameters.get("project_revision", 1)),
            input_fingerprint=fingerprint,
            cache_key=hashlib.sha256((fingerprint + result_type).encode()).hexdigest(),
            result_type=result_type,
            payload=plan,
        )
        return BusinessExecution(result, (StagedArtifact("effects", "json", output),))

    execution = execute_business_handler(job, args.result.parent, args.result, "P09", handler)
    return 0 if execution.outcome == "succeeded" else 1


def project_effect_plan(result: BusinessResultManifest, project_dir: Path) -> None:
    manifest_path = project_dir / "project.json"
    manifest = ProjectManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    record = EffectPlanRecord.model_validate(result.payload)
    page_id = UUID(str(record.plan.page_id))
    pages = list(manifest.pages)
    for index, page in enumerate(pages):
        if page.id == page_id:
            pages[index] = page.model_copy(update={"effect_plan": record})
            break
    else:
        raise ValueError(f"effect page does not exist: {page_id}")
    updated = manifest.model_copy(
        update={
            "pages": pages,
            "audit_log": [
                *manifest.audit_log,
                AuditEvent(
                    action="effect_plan_regenerated",
                    occurred_at=datetime.now(UTC),
                    details={"page_id": str(page_id), "revision": record.revision},
                ),
            ],
        }
    )
    temporary = manifest_path.with_name(".project.json.s1.tmp")
    temporary.write_text(updated.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(manifest_path)


if __name__ == "__main__":
    raise SystemExit(main())
