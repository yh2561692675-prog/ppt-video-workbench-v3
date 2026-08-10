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


class AudioRejected(ValueError):
    pass


def build_audio_pipeline(metadata: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any]:
    duration_ms = int(metadata.get("duration_ms", 0))
    sample_rate = int(metadata.get("sample_rate", 0))
    channels = int(metadata.get("channels", 0))
    if duration_ms <= 0 or sample_rate <= 0 or channels not in {1, 2}:
        raise AudioRejected("audio metadata is invalid")
    if not pages:
        raise AudioRejected("audio pipeline requires page durations")
    total = sum(int(page.get("duration_ms", 0)) for page in pages)
    if total != duration_ms:
        raise AudioRejected("page durations do not cover the audio duration")
    start = 0
    segments = []
    for page in pages:
        page_duration = int(page["duration_ms"])
        if page_duration <= 0 or not isinstance(page.get("page_id"), str):
            raise AudioRejected("page audio duration is invalid")
        segments.append(
            {
                "page_id": page["page_id"],
                "start_ms": start,
                "end_ms": start + page_duration,
            }
        )
        start += page_duration
    return {
        "normalized": {
            "duration_ms": duration_ms,
            "sample_rate": sample_rate,
            "channels": channels,
        },
        "segments": segments,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    job = JobEnvelope.model_validate_json(args.request.read_text(encoding="utf-8"))

    def handler(received: JobEnvelope, attempt_root: Path) -> BusinessExecution:
        metadata = received.parameters.get("metadata")
        pages = received.parameters.get("pages")
        if not isinstance(metadata, dict) or not isinstance(pages, list):
            raise AudioRejected("parameters must contain metadata and pages")
        pipeline = build_audio_pipeline(
            metadata, [item for item in pages if isinstance(item, dict)]
        )
        output = attempt_root / "audio.json"
        output.write_text(
            json.dumps(pipeline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        fingerprint = business_input_fingerprint(received)
        result = BusinessResultManifest(
            schema_version="1.0",
            module_id="P07",
            job_type=received.job_type,
            project_id=received.project_id,
            project_revision=int(received.parameters.get("project_revision", 1)),
            input_fingerprint=fingerprint,
            cache_key=hashlib.sha256((fingerprint + "audio_pipeline").encode()).hexdigest(),
            result_type="audio_pipeline",
            payload=pipeline,
        )
        return BusinessExecution(result, (StagedArtifact("audio", "json", output),))

    execution = execute_business_handler(job, args.result.parent, args.result, "P07", handler)
    return 0 if execution.outcome == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
