from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from typing import Any

from peripheral_contracts import BusinessResultManifest, JobEnvelope

from workbench.business_modules.p08_subtitle.models import (
    SubtitleArtifactDescriptor,
    SubtitleBuildParameters,
    SubtitleTimelinePayload,
)
from workbench.business_modules.runtime import (
    BusinessExecution,
    StagedArtifact,
    business_input_fingerprint,
    business_parameters,
    execute_business_handler,
    project_revision,
)
from workbench.domain.audio import SubtitleArtifact
from workbench.domain.enums import NodeStatus
from workbench.domain.models import AuditEvent, ProjectManifest
from workbench.subtitles.models import SubtitlePageRange
from workbench.subtitles.service import (
    build_heygen_word_timestamps,
    build_subtitle_timeline,
    format_srt,
)


def build_subtitle_payload(
    pages: list[dict[str, Any]], words: list[dict[str, Any]], duration_ms: int
) -> dict[str, Any]:
    """Legacy pure helper retained for older callers."""
    from workbench.audio.models import TranscriptWord

    ranges = [SubtitlePageRange.model_validate(page) for page in pages]
    transcript_words = [TranscriptWord.model_validate(word) for word in words]
    timeline = build_subtitle_timeline(ranges, transcript_words, duration_ms=duration_ms)
    return {"timeline": timeline.model_dump(mode="json"), "srt": format_srt(timeline)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    job = JobEnvelope.model_validate_json(args.request.read_text(encoding="utf-8-sig"))
    execution = execute_business_handler(job, args.result.parent, args.result, "P08", _handle)
    return 0 if execution.outcome == "succeeded" else 1


def _handle(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    if job.job_type != "subtitle.build":
        raise ValueError(f"unsupported P08 job type: {job.job_type}")
    parameters = SubtitleBuildParameters.model_validate(business_parameters(job))
    ranges = [
        SubtitlePageRange(
            page_id=item.page_id,
            page_order=item.page_order,
            start_ms=item.start_ms,
            end_ms=item.end_ms,
        )
        for item in parameters.pages
    ]
    words = list(parameters.words)
    if parameters.route == "heygen":
        words = build_heygen_word_timestamps(
            ranges, {item.page_id: item.narration_text for item in parameters.pages}
        )
    timeline = build_subtitle_timeline(ranges, words, duration_ms=parameters.duration_ms)
    srt = format_srt(timeline)
    timeline_path = attempt_root / "subtitle-timeline.json"
    srt_path = attempt_root / "subtitle.srt"
    timeline_path.write_text(timeline.model_dump_json(indent=2) + "\n", encoding="utf-8")
    srt_path.write_text(srt, encoding="utf-8", newline="\n")
    descriptors = (
        _descriptor("subtitle-timeline", "06_字幕/字幕时间轴.json", timeline_path),
        _descriptor("subtitle-srt", "06_字幕/字幕.srt", srt_path),
    )
    payload = SubtitleTimelinePayload(
        route=parameters.route,
        generated_at=job.created_at,
        timeline=timeline,
        srt=srt,
        narration_revisions={item.page_id: item.narration_revision_id for item in parameters.pages},
        artifacts=descriptors,
    )
    fingerprint = business_input_fingerprint(job)
    result = BusinessResultManifest(
        schema_version="1.0",
        module_id="P08",
        job_type=job.job_type,
        project_id=job.project_id,
        project_revision=project_revision(job),
        input_fingerprint=fingerprint,
        cache_key=hashlib.sha256(f"{fingerprint}:subtitle.build".encode()).hexdigest(),
        result_type="subtitle_timeline",
        payload=payload.model_dump(mode="json"),
    )
    return BusinessExecution(
        result,
        (
            StagedArtifact("subtitle-timeline", "json", timeline_path),
            StagedArtifact("subtitle-srt", "srt", srt_path),
        ),
    )


def _descriptor(logical_name: str, relative_path: str, path: Path) -> SubtitleArtifactDescriptor:
    content = path.read_bytes()
    return SubtitleArtifactDescriptor(
        logical_name=logical_name,
        relative_path=relative_path,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def project_subtitle_timeline(result: BusinessResultManifest, project_dir: Path) -> None:
    payload = SubtitleTimelinePayload.model_validate(result.payload)
    manifest_path = project_dir / "project.json"
    manifest = ProjectManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    pages = {page.id: page for page in manifest.pages}
    routes = {
        page.audio.source
        for page in manifest.pages
        if page.audio is not None and page.audio.status is NodeStatus.COMPLETED
    }
    if routes != {payload.route}:
        raise ValueError("P08_GATE_BLOCKED: project audio route is incomplete or mixed")
    if set(payload.narration_revisions) != set(pages):
        raise ValueError("P08_GATE_BLOCKED: subtitle result does not cover every project page")
    for page_id, revision_id in payload.narration_revisions.items():
        page = pages[page_id]
        if (
            page.narration is None
            or page.audio is None
            or page.narration.revision_id != revision_id
            or page.narration.confirmed_revision_id != revision_id
            or page.audio.narration_revision_id != revision_id
        ):
            raise ValueError("STALE_NARRATION_REVISION: subtitle input is no longer current")
    by_logical = {item.logical_name: item for item in payload.artifacts}
    timeline = by_logical["subtitle-timeline"]
    srt = by_logical["subtitle-srt"]
    updated = manifest.model_copy(
        update={
            "subtitle_artifact": SubtitleArtifact(
                timeline_relative_path=timeline.relative_path,
                srt_relative_path=srt.relative_path,
                timeline_sha256=timeline.sha256,
                srt_sha256=srt.sha256,
            ),
            "video_preflight": None,
            "video_export": None,
            "audit_log": [
                *manifest.audit_log,
                AuditEvent(
                    action="subtitle_timeline_projected",
                    occurred_at=payload.generated_at,
                    details={
                        "route": payload.route,
                        "cue_count": len(payload.timeline.cues),
                        "timeline_sha256": timeline.sha256,
                        "srt_sha256": srt.sha256,
                    },
                ),
            ],
        }
    )
    temporary = manifest_path.with_name(".project.json.s1.tmp")
    temporary.write_text(updated.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, manifest_path)


if __name__ == "__main__":
    raise SystemExit(main())
