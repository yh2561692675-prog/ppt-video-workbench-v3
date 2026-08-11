from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from peripheral_contracts import BusinessResultManifest, JobEnvelope

from .runtime import BusinessExecution, StagedArtifact, execute_business_handler, project_revision

BusinessModuleId = Literal["P03", "P04", "P05", "P06", "P07", "P08", "P09", "P10", "P11", "P12"]


def generic_main(
    module_id: BusinessModuleId,
    result_type: str | dict[str, str],
    *,
    output_name: str = "result.json",
) -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    arguments = parser.parse_args()
    job = JobEnvelope.model_validate_json(arguments.request.read_text(encoding="utf-8"))

    def handler(received: JobEnvelope, attempt_root: Path) -> BusinessExecution:
        payload: dict[str, Any] = {
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
        output = attempt_root / output_name
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        fingerprint = hashlib.sha256(received.model_dump_json().encode()).hexdigest()
        selected_result_type = (
            result_type.get(received.job_type, next(iter(result_type.values())))
            if isinstance(result_type, dict)
            else result_type
        )
        business = BusinessResultManifest(
            schema_version="1.0",
            module_id=module_id,
            job_type=received.job_type,
            project_id=received.project_id,
            project_revision=project_revision(received),
            input_fingerprint=fingerprint,
            cache_key=hashlib.sha256((fingerprint + selected_result_type).encode()).hexdigest(),
            result_type=selected_result_type,
            payload=payload,
        )
        return BusinessExecution(
            business, (StagedArtifact(output_name.removesuffix(".json"), "json", output),)
        )

    execution = execute_business_handler(
        job, arguments.result.parent, arguments.result, module_id, handler
    )
    return 0 if execution.outcome == "succeeded" else 1
