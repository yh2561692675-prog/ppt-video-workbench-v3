from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from typing import Any
from uuid import uuid5

from peripheral_contracts import BusinessResultManifest, JobEnvelope

from workbench.business_modules.p10_preflight.models import (
    ArtifactDescriptor,
    PreflightReportPayload,
    PreflightRunParameters,
    PreviewBuildParameters,
    VideoPreviewPayload,
)
from workbench.business_modules.runtime import (
    BusinessExecution,
    StagedArtifact,
    business_input_fingerprint,
    business_parameters,
    execute_business_handler,
    project_revision,
)
from workbench.domain.issues import IssueLevel, PreflightReport
from workbench.domain.models import AuditEvent, ProjectManifest, VideoPreflightRecord
from workbench.preflight.engine import PreflightEngine


def run_preflight(project: ProjectManifest, workspace_root: Path) -> dict[str, Any]:
    report = PreflightEngine(workspace_root).run_preflight(project)
    return report.model_dump(mode="json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    job = JobEnvelope.model_validate_json(args.request.read_text(encoding="utf-8-sig"))
    execution = execute_business_handler(job, args.result.parent, args.result, "P10", _handle)
    return 0 if execution.outcome == "succeeded" else 1


def _handle(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    if job.job_type == "preview.build":
        return _preview(job, attempt_root)
    if job.job_type == "preflight.run":
        return _preflight(job, attempt_root)
    raise ValueError(f"unsupported P10 job type: {job.job_type}")


def _preview(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    parameters = PreviewBuildParameters.model_validate(business_parameters(job))
    preview = parameters.preview
    if preview.props is not None:
        preview = preview.model_copy(
            update={
                "props": preview.props.model_copy(
                    update={"reduced_motion": parameters.reduced_motion}
                )
            }
        )
    output = attempt_root / "video-preview.json"
    output.write_text(preview.model_dump_json(indent=2) + "\n", encoding="utf-8")
    descriptor = _descriptor("video-preview", "07_视频/video-preview.json", output)
    payload = VideoPreviewPayload(
        preview=preview,
        reduced_motion=parameters.reduced_motion,
        generated_at=job.created_at,
        artifact=descriptor,
    )
    return _execution(
        job,
        "video_preview",
        payload.model_dump(mode="json"),
        (StagedArtifact("video-preview", "json", output),),
    )


def _preflight(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    parameters = PreflightRunParameters.model_validate(business_parameters(job))
    project = parameters.project_manifest
    snapshot_root = attempt_root / project.project_dir
    snapshot_root.mkdir(parents=True, exist_ok=True)
    report = PreflightEngine(attempt_root).run_preflight(
        project, scope=set(parameters.scope), previous=parameters.previous_report
    )
    _validate_allowed(report)
    json_path = attempt_root / "preflight-report.json"
    markdown_path = attempt_root / "preflight-report.md"
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8", newline="\n")
    descriptors = (
        _descriptor("preflight-report-json", "09_日志/预检/预检报告.json", json_path),
        _descriptor("preflight-report-md", "09_日志/预检/预检报告.md", markdown_path),
    )
    payload = PreflightReportPayload(
        report=report,
        generated_at=job.created_at,
        artifacts=descriptors,
    )
    return _execution(
        job,
        "preflight_report",
        payload.model_dump(mode="json"),
        (
            StagedArtifact("preflight-report-json", "json", json_path),
            StagedArtifact("preflight-report-md", "markdown", markdown_path),
        ),
    )


def _execution(
    job: JobEnvelope,
    result_type: str,
    payload: dict[str, Any],
    artifacts: tuple[StagedArtifact, ...],
) -> BusinessExecution:
    fingerprint = business_input_fingerprint(job)
    return BusinessExecution(
        BusinessResultManifest(
            schema_version="1.0",
            module_id="P10",
            job_type=job.job_type,
            project_id=job.project_id,
            project_revision=project_revision(job),
            input_fingerprint=fingerprint,
            cache_key=hashlib.sha256(f"{fingerprint}:{job.job_type}".encode()).hexdigest(),
            result_type=result_type,
            payload=payload,
        ),
        artifacts,
    )


def _descriptor(logical_name: str, relative_path: str, path: Path) -> ArtifactDescriptor:
    content = path.read_bytes()
    return ArtifactDescriptor(
        logical_name=logical_name,
        relative_path=relative_path,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def _validate_allowed(report: PreflightReport) -> None:
    expected = not any(
        issue.blocking
        or (
            issue.level in {IssueLevel.CONFIRMATION, IssueLevel.REQUIRED_WARNING}
            and not issue.confirmed
        )
        for issue in report.issues
    )
    if report.allowed != expected:
        raise ValueError("preflight allowed flag does not match issue gates")


def _markdown(report: PreflightReport) -> str:
    lines = [
        "# Preflight Report",
        "",
        f"- Project: `{report.project_id}`",
        f"- Checked: `{report.checked_at.isoformat()}`",
        f"- Allowed: `{str(report.allowed).lower()}`",
        f"- Fingerprint: `{report.input_fingerprint}`",
        "",
        "## Issues",
        "",
    ]
    if not report.issues:
        lines.append("No issues.")
    for issue in report.issues:
        lines.extend(
            [
                f"### {issue.level.value}: {issue.code}",
                "",
                f"- Message: {issue.message}",
                f"- Action: {issue.action}",
                f"- Confirmed: {str(issue.confirmed).lower()}",
                f"- Fingerprint: `{issue.fingerprint}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def project_video_preview(result: BusinessResultManifest, project_dir: Path) -> None:
    payload = VideoPreviewPayload.model_validate(result.payload)
    manifest_path = project_dir / "project.json"
    manifest = ProjectManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    preview = payload.preview
    props_digest = (
        hashlib.sha256(preview.props.model_dump_json().encode()).hexdigest()
        if preview.props is not None
        else None
    )
    updated = manifest.model_copy(
        update={
            "video_preflight": VideoPreflightRecord(
                id=uuid5(manifest.id, f"P10:preview:{result.cache_key}"),
                allowed=preview.allowed,
                issue_codes=[item.code for item in preview.issues],
                props_cache_key=props_digest,
                reduced_motion=payload.reduced_motion,
                checked_at=payload.generated_at,
            ),
            "video_export": None,
        }
    )
    _write_manifest(manifest_path, updated)


def project_preflight_report(result: BusinessResultManifest, project_dir: Path) -> None:
    payload = PreflightReportPayload.model_validate(result.payload)
    report = payload.report
    _validate_allowed(report)
    manifest_path = project_dir / "project.json"
    manifest = ProjectManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if report.project_id != manifest.id:
        raise ValueError("preflight report project identity mismatch")
    updated = manifest.model_copy(
        update={
            "preflight_report": report,
            "preflight_history": [*manifest.preflight_history, report.input_fingerprint],
            "video_export": None,
            "audit_log": [
                *manifest.audit_log,
                AuditEvent(
                    action="preflight_completed",
                    occurred_at=payload.generated_at,
                    details={"allowed": report.allowed, "issue_count": len(report.issues)},
                ),
            ],
        }
    )
    _write_manifest(manifest_path, updated)


def _write_manifest(path: Path, manifest: ProjectManifest) -> None:
    temporary = path.with_name(".project.json.s1.tmp")
    temporary.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


if __name__ == "__main__":
    raise SystemExit(main())
