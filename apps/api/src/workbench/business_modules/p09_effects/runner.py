from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
from typing import Any
from uuid import UUID

from peripheral_contracts import BusinessResultManifest, JobEnvelope

from workbench.business_modules.p09_effects.models import (
    ArtifactDescriptor,
    EffectPlanParameters,
    EffectPlanPayload,
    ProjectVideoPropsPayload,
    VideoPropsBuildParameters,
)
from workbench.business_modules.runtime import (
    BusinessExecution,
    StagedArtifact,
    business_input_fingerprint,
    business_parameters,
    execute_business_handler,
    project_revision,
)
from workbench.domain.effects import validate_record_hash
from workbench.domain.models import AuditEvent, ProjectManifest
from workbench.effects.planner import EffectPlanner, EffectPlanningInput


def plan_effect(parameters: dict[str, Any]) -> dict[str, Any]:
    value = EffectPlanningInput.model_validate(parameters)
    return EffectPlanner().plan(value).model_dump(mode="json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    job = JobEnvelope.model_validate_json(args.request.read_text(encoding="utf-8-sig"))
    execution = execute_business_handler(job, args.result.parent, args.result, "P09", _handle)
    return 0 if execution.outcome == "succeeded" else 1


def _handle(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    if job.job_type == "effect.plan":
        return _plan(job, attempt_root)
    if job.job_type == "video.props.build":
        return _props(job, attempt_root)
    raise ValueError(f"unsupported P09 job type: {job.job_type}")


def _plan(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    parameters = EffectPlanParameters.model_validate(business_parameters(job))
    planning = EffectPlanningInput.model_validate(parameters.model_dump(exclude={"reduced_motion"}))
    record = EffectPlanner().plan(planning)
    output = attempt_root / "effect-plan-v2.json"
    output.write_text(record.model_dump_json(indent=2) + "\n", encoding="utf-8")
    descriptor = _descriptor("effect-plan-v2", "07_视频/效果计划.json", output)
    payload = EffectPlanPayload(
        record=record,
        generated_at=job.created_at,
        artifact=descriptor,
    )
    return _execution(
        job,
        "effect_plan_v2",
        payload.model_dump(mode="json"),
        (StagedArtifact("effect-plan-v2", "json", output),),
    )


def _props(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    parameters = VideoPropsBuildParameters.model_validate(business_parameters(job))
    props = parameters.props.model_copy(
        update={"subtitle_placements": list(parameters.layout_report)}
    )
    output = attempt_root / "project-video-props.json"
    output.write_text(props.model_dump_json(indent=2) + "\n", encoding="utf-8")
    descriptor = _descriptor("project-video-props", "07_视频/project-video-props.json", output)
    payload = ProjectVideoPropsPayload(
        props=props,
        layout_report=parameters.layout_report,
        generated_at=job.created_at,
        artifact=descriptor,
    )
    return _execution(
        job,
        "project_video_props",
        payload.model_dump(mode="json"),
        (StagedArtifact("project-video-props", "json", output),),
    )


def _execution(
    job: JobEnvelope,
    result_type: str,
    payload: dict[str, Any],
    artifacts: tuple[StagedArtifact, ...],
) -> BusinessExecution:
    fingerprint = business_input_fingerprint(job)
    result = BusinessResultManifest(
        schema_version="1.0",
        module_id="P09",
        job_type=job.job_type,
        project_id=job.project_id,
        project_revision=project_revision(job),
        input_fingerprint=fingerprint,
        cache_key=hashlib.sha256(f"{fingerprint}:{job.job_type}".encode()).hexdigest(),
        result_type=result_type,
        payload=payload,
    )
    return BusinessExecution(result, artifacts)


def _descriptor(logical_name: str, relative_path: str, path: Path) -> ArtifactDescriptor:
    content = path.read_bytes()
    return ArtifactDescriptor(
        logical_name=logical_name,
        relative_path=relative_path,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def project_effect_plan(result: BusinessResultManifest, project_dir: Path) -> None:
    payload = EffectPlanPayload.model_validate(result.payload)
    record = validate_record_hash(payload.record)
    manifest_path = project_dir / "project.json"
    manifest = ProjectManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
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
            "video_preflight": None,
            "video_export": None,
            "audit_log": [
                *manifest.audit_log,
                AuditEvent(
                    action="effect_plan_regenerated",
                    occurred_at=payload.generated_at,
                    details={
                        "page_id": str(page_id),
                        "revision": record.revision,
                        "plan_hash": record.plan_hash,
                    },
                ),
            ],
        }
    )
    _write_manifest(manifest_path, updated)


def project_video_props(result: BusinessResultManifest, project_dir: Path) -> None:
    payload = ProjectVideoPropsPayload.model_validate(result.payload)
    manifest_path = project_dir / "project.json"
    manifest = ProjectManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if payload.props.project_id != manifest.id:
        raise ValueError("video props project identity does not match target project")
    if set(page.page_id for page in payload.props.pages) != set(page.id for page in manifest.pages):
        raise ValueError("video props do not cover every project page")
    updated = manifest.model_copy(
        update={
            "video_preflight": None,
            "video_export": None,
            "audit_log": [
                *manifest.audit_log,
                AuditEvent(
                    action="project_video_props_projected",
                    occurred_at=payload.generated_at,
                    details={
                        "schema_version": payload.props.schema_version,
                        "page_count": len(payload.props.pages),
                        "artifact_sha256": payload.artifact.sha256,
                    },
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
