from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from peripheral_contracts import BusinessResultManifest, JobEnvelope

from workbench.business_modules.runtime import (
    BusinessExecution,
    StagedArtifact,
    business_input_fingerprint,
    execute_business_handler,
)
from workbench.domain.extraction import PageExtraction
from workbench.domain.matching import PageMatch
from workbench.domain.models import AuditEvent, ProjectManifest
from workbench.domain.outline import OutlineDocument
from workbench.matching.page_matcher import match_outline_to_pages


class MatchingRejected(ValueError):
    pass


def match_payload(
    outline: dict[str, object], pages: list[dict[str, object]]
) -> list[dict[str, object]]:
    document = OutlineDocument.model_validate(outline)
    extractions = [PageExtraction.model_validate(page) for page in pages]
    return [
        item.model_dump(mode="json")
        for item in match_outline_to_pages(document, extractions).matches
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    job = JobEnvelope.model_validate_json(args.request.read_text(encoding="utf-8"))

    def handler(received: JobEnvelope, attempt_root: Path) -> BusinessExecution:
        outline = received.parameters.get("outline")
        pages = received.parameters.get("pages")
        if not isinstance(outline, dict) or not isinstance(pages, list):
            raise MatchingRejected("parameters must contain outline and pages")
        matches = match_payload(outline, pages)
        output = attempt_root / "matches.json"
        output.write_text(
            json.dumps({"matches": matches}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        fingerprint = business_input_fingerprint(received)
        result = BusinessResultManifest(
            schema_version="1.0",
            module_id="P05",
            job_type=received.job_type,
            project_id=received.project_id,
            project_revision=int(received.parameters.get("project_revision", 1)),
            input_fingerprint=fingerprint,
            cache_key=hashlib.sha256((fingerprint + "page_matches").encode()).hexdigest(),
            result_type="page_matches",
            payload={"matches": matches},
        )
        return BusinessExecution(result, (StagedArtifact("matches", "json", output),))

    execution = execute_business_handler(job, args.result.parent, args.result, "P05", handler)
    return 0 if execution.outcome == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())


def project_page_matches(result: BusinessResultManifest, project_dir: Path) -> None:
    manifest_path = project_dir / "project.json"
    manifest = ProjectManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    incoming = [
        PageMatch.model_validate(item)
        for item in result.payload.get("matches", [])
        if isinstance(item, dict)
    ]
    current = {item.page_id: item for item in manifest.matches}
    for item in incoming:
        previous = current.get(item.page_id)
        if previous is not None and previous.decision_source == "manual":
            current[item.page_id] = item.model_copy(
                update={
                    "selected_outline_ref": previous.selected_outline_ref,
                    "score": previous.score,
                    "decision_source": "manual",
                    "needs_confirmation": previous.needs_confirmation,
                }
            )
        else:
            current[item.page_id] = item
    updated = manifest.model_copy(
        update={
            "matches": sorted(current.values(), key=lambda item: item.page_order),
            "audit_log": [
                *manifest.audit_log,
                AuditEvent(
                    action="materials_matched",
                    occurred_at=datetime.now(UTC),
                    details={"match_count": len(incoming)},
                ),
            ],
        }
    )
    temporary = manifest_path.with_name(".project.json.s1.tmp")
    temporary.write_text(updated.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(manifest_path)
