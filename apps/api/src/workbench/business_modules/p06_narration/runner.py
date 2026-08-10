from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from peripheral_contracts import BusinessResultManifest, JobEnvelope

from workbench.business_modules.runtime import (
    BusinessExecution,
    StagedArtifact,
    business_input_fingerprint,
    execute_business_handler,
)
from workbench.domain.models import AuditEvent, NarrationRecord, ProjectManifest

_SECRET = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")


def normalize_assignments(assignments: list[dict[str, object]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in assignments:
        page_id = item.get("page_id")
        text = item.get("text")
        if not isinstance(page_id, str) or not isinstance(text, str):
            raise ValueError("narration assignment requires page_id and text")
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("narration text must not be empty")
        UUID(page_id)
        author = item.get("author", "外围平台")
        normalized.append({"page_id": page_id, "text": cleaned, "author": str(author)})
    return normalized


def safe_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    def clean(value: Any) -> Any:
        if isinstance(value, str):
            return _SECRET.sub(r"\1[REDACTED]", value)
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if "key" in key.lower() or "token" in key.lower() else clean(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(parameters)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    job = JobEnvelope.model_validate_json(args.request.read_text(encoding="utf-8"))

    def handler(received: JobEnvelope, attempt_root: Path) -> BusinessExecution:
        assignments_raw = received.parameters.get("assignments", [])
        if not isinstance(assignments_raw, list):
            raise ValueError("parameters.assignments must be a list")
        assignments = normalize_assignments(
            [item for item in assignments_raw if isinstance(item, dict)]
        )
        output = attempt_root / "narration.json"
        output.write_text(
            json.dumps({"assignments": assignments}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        fingerprint = business_input_fingerprint(received)
        result = BusinessResultManifest(
            schema_version="1.0",
            module_id="P06",
            job_type=received.job_type,
            project_id=received.project_id,
            project_revision=int(received.parameters.get("project_revision", 1)),
            input_fingerprint=fingerprint,
            cache_key=hashlib.sha256((fingerprint + "narration_revisions").encode()).hexdigest(),
            result_type="narration_revisions",
            payload={"assignments": assignments},
        )
        return BusinessExecution(result, (StagedArtifact("narration", "json", output),))

    execution = execute_business_handler(job, args.result.parent, args.result, "P06", handler)
    return 0 if execution.outcome == "succeeded" else 1


def project_narration_revisions(result: BusinessResultManifest, project_dir: Path) -> None:
    manifest_path = project_dir / "project.json"
    manifest = ProjectManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    assignments = normalize_assignments(
        [item for item in result.payload.get("assignments", []) if isinstance(item, dict)]
    )
    by_id = {page.id: page for page in manifest.pages}
    now = datetime.now(UTC)
    for assignment in assignments:
        page_id = UUID(assignment["page_id"])
        page = by_id.get(page_id)
        if page is None:
            raise ValueError(f"narration page does not exist: {page_id}")
        current = page.narration
        narration = NarrationRecord(
            id=current.id if current else uuid4(),
            revision_id=uuid4(),
            text=assignment["text"],
            author=assignment["author"],
            version=(current.version + 1 if current else 1),
            source_refs=["peripheral:P06"],
            updated_at=now,
        )
        by_id[page_id] = page.model_copy(update={"narration": narration})
    updated = manifest.model_copy(
        update={
            "pages": sorted(by_id.values(), key=lambda item: item.order),
            "audit_log": [
                *manifest.audit_log,
                AuditEvent(
                    action="narration_revisions_imported",
                    occurred_at=now,
                    details={"count": len(assignments)},
                ),
            ],
        }
    )
    temporary = manifest_path.with_name(".project.json.s1.tmp")
    temporary.write_text(updated.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(manifest_path)


if __name__ == "__main__":
    raise SystemExit(main())
