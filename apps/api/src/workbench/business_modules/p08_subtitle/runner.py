from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from peripheral_contracts import BusinessResultManifest, JobEnvelope

from workbench.audio.models import TranscriptWord
from workbench.business_modules.runtime import (
    BusinessExecution,
    StagedArtifact,
    business_input_fingerprint,
    execute_business_handler,
)
from workbench.subtitles.models import SubtitlePageRange
from workbench.subtitles.service import build_subtitle_timeline, format_srt


def build_subtitle_payload(
    pages: list[dict[str, Any]], words: list[dict[str, Any]], duration_ms: int
) -> dict[str, Any]:
    ranges = [SubtitlePageRange.model_validate(page) for page in pages]
    transcript_words = [TranscriptWord.model_validate(word) for word in words]
    timeline = build_subtitle_timeline(ranges, transcript_words, duration_ms=duration_ms)
    return {"timeline": timeline.model_dump(mode="json"), "srt": format_srt(timeline)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    job = JobEnvelope.model_validate_json(args.request.read_text(encoding="utf-8"))

    def handler(received: JobEnvelope, attempt_root: Path) -> BusinessExecution:
        pages = received.parameters.get("pages")
        words = received.parameters.get("words")
        duration_ms = received.parameters.get("duration_ms")
        if (
            not isinstance(pages, list)
            or not isinstance(words, list)
            or not isinstance(duration_ms, int)
        ):
            raise ValueError("subtitle parameters are incomplete")
        payload = build_subtitle_payload(
            [item for item in pages if isinstance(item, dict)],
            [item for item in words if isinstance(item, dict)],
            duration_ms,
        )
        output = attempt_root / "subtitle.json"
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        fingerprint = business_input_fingerprint(received)
        result = BusinessResultManifest(
            schema_version="1.0",
            module_id="P08",
            job_type=received.job_type,
            project_id=received.project_id,
            project_revision=int(received.parameters.get("project_revision", 1)),
            input_fingerprint=fingerprint,
            cache_key=hashlib.sha256((fingerprint + "subtitle_timeline").encode()).hexdigest(),
            result_type="subtitle_timeline",
            payload=payload,
        )
        return BusinessExecution(result, (StagedArtifact("subtitle", "json", output),))

    execution = execute_business_handler(job, args.result.parent, args.result, "P08", handler)
    return 0 if execution.outcome == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
