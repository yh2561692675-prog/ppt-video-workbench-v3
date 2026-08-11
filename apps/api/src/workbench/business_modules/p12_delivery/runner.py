from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any

from peripheral_contracts import BusinessResultManifest, JobEnvelope

from workbench.business_modules.p12_delivery.models import (
    ArtifactDescriptor,
    DeliveryArchiveParameters,
    DeliveryDecisionPayload,
    MediaProbe,
    QualityReportPayload,
    QualityVerifyParameters,
)
from workbench.business_modules.p12_delivery.policy import verify_package
from workbench.business_modules.runtime import (
    BusinessExecution,
    StagedArtifact,
    business_input_fingerprint,
    business_parameters,
    execute_business_handler,
    project_revision,
)
from workbench.domain.models import AuditEvent, ProjectManifest


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
    job = JobEnvelope.model_validate_json(args.request.read_text(encoding="utf-8-sig"))
    execution = execute_business_handler(job, args.result.parent, args.result, "P12", _handle)
    return 0 if execution.outcome == "succeeded" else 1


def _handle(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    if job.job_type == "quality.verify":
        return _quality(job, attempt_root)
    if job.job_type == "delivery.archive":
        return _archive(job, attempt_root)
    raise ValueError(f"unsupported P12 job type: {job.job_type}")


def _quality(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    parameters = QualityVerifyParameters.model_validate(business_parameters(job))
    package = _single_input(job, attempt_root)
    manifest = parameters.package_manifest
    expected = {item.relative_path: (item.size_bytes, item.sha256) for item in manifest.files}
    checks = verify_package(
        package,
        manifest.package.sha256,
        expected,
        _probe_package_video(package, attempt_root),
        parameters.policy,
    )
    missing_evidence = tuple(
        item for item in parameters.policy.required_evidence if item not in parameters.evidence
    )
    json_path = attempt_root / "quality-report.json"
    md_path = attempt_root / "quality-report.md"
    provisional = QualityReportPayload(
        automated_passed=all(item.passed for item in checks),
        checks=tuple(checks),
        package_sha256=manifest.package.sha256,
        missing_evidence=missing_evidence,
        required_signers=parameters.policy.required_signers,
        generated_at=job.created_at,
        artifacts=(
            ArtifactDescriptor(
                logical_name="quality-report-json",
                relative_path="08_输出/验收/quality-report.json",
                size_bytes=1,
                sha256="0" * 64,
            ),
            ArtifactDescriptor(
                logical_name="quality-report-md",
                relative_path="08_输出/验收/quality-report.md",
                size_bytes=1,
                sha256="0" * 64,
            ),
        ),
    )
    json_path.write_text(provisional.model_dump_json(indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_quality_markdown(provisional), encoding="utf-8", newline="\n")
    report = provisional.model_copy(
        update={
            "artifacts": (
                _descriptor("quality-report-json", "08_输出/验收/quality-report.json", json_path),
                _descriptor("quality-report-md", "08_输出/验收/quality-report.md", md_path),
            )
        }
    )
    # Rewrite JSON with final artifact metadata, then update its self descriptor once.
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    final_json = _descriptor("quality-report-json", "08_输出/验收/quality-report.json", json_path)
    report = report.model_copy(update={"artifacts": (final_json, report.artifacts[1])})
    return _execution(
        job,
        "quality_report",
        report.model_dump(mode="json"),
        (
            StagedArtifact("quality-report-json", "json", json_path),
            StagedArtifact("quality-report-md", "markdown", md_path),
        ),
    )


def _archive(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    parameters = DeliveryArchiveParameters.model_validate(business_parameters(job))
    package = _single_input(job, attempt_root)
    report = parameters.quality_report
    package_sha = _sha256(package)
    reasons: list[str] = []
    if package_sha != report.package_sha256:
        reasons.append("package_hash_changed")
    if not report.automated_passed:
        reasons.append("automated_quality_failed")
    missing_evidence = set(report.missing_evidence) - set(parameters.evidence)
    if missing_evidence:
        reasons.append("required_evidence_missing")
    missing_signers = set(report.required_signers) - set(parameters.signatures)
    if missing_signers:
        reasons.append("required_signature_missing")
    invalid_signatures = [
        signer for signer, value in parameters.signatures.items() if len(value.strip()) < 8
    ]
    if invalid_signatures:
        reasons.append("invalid_signature")
    artifacts: tuple[StagedArtifact, ...] = ()
    archive_descriptor = None
    archive_id = None
    if not reasons:
        archive_id = f"{job.created_at.astimezone().strftime('%Y%m%dT%H%M%SZ')}-{package_sha[:12]}"
        target = attempt_root / f"delivery-{archive_id}.zip"
        shutil.copyfile(package, target)
        archive_descriptor = _descriptor(
            "delivery-archive", f"08_输出/交付/{archive_id}/制作包.zip", target
        )
        artifacts = (StagedArtifact("delivery-archive", "zip", target),)
    decision = DeliveryDecisionPayload(
        decision="blocked" if reasons else "archived",
        reasons=tuple(reasons),
        package_sha256=package_sha,
        archive_id=archive_id,
        archive=archive_descriptor,
        signed_by=tuple(sorted(parameters.signatures)),
        generated_at=job.created_at,
    )
    return _execution(job, "delivery_decision", decision.model_dump(mode="json"), artifacts)


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
            module_id="P12",
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


def project_quality_report(result: BusinessResultManifest, project_dir: Path) -> None:
    report = QualityReportPayload.model_validate(result.payload)
    manifest_path = project_dir / "project.json"
    manifest = ProjectManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    updated = manifest.model_copy(
        update={
            "audit_log": [
                *manifest.audit_log,
                AuditEvent(
                    action="quality_verification_completed",
                    occurred_at=report.generated_at,
                    details={
                        "automated_passed": report.automated_passed,
                        "package_sha256": report.package_sha256,
                        "failed_codes": [item.code for item in report.checks if not item.passed],
                    },
                ),
            ]
        }
    )
    _write_manifest(manifest_path, updated)


def project_delivery_decision(result: BusinessResultManifest, project_dir: Path) -> None:
    decision = DeliveryDecisionPayload.model_validate(result.payload)
    manifest_path = project_dir / "project.json"
    manifest = ProjectManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if decision.decision == "archived":
        _append_archive_index(project_dir, decision)
    updated = manifest.model_copy(
        update={
            "audit_log": [
                *manifest.audit_log,
                AuditEvent(
                    action=(
                        "delivery_archived"
                        if decision.decision == "archived"
                        else "delivery_blocked"
                    ),
                    occurred_at=decision.generated_at,
                    details={
                        "archive_id": decision.archive_id,
                        "package_sha256": decision.package_sha256,
                        "reasons": list(decision.reasons),
                        "signed_by": list(decision.signed_by),
                    },
                ),
            ]
        }
    )
    _write_manifest(manifest_path, updated)


def _append_archive_index(project_dir: Path, decision: DeliveryDecisionPayload) -> None:
    target = project_dir / "08_输出" / "交付" / "index.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        entries = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        entries = []
    if not isinstance(entries, list):
        raise ValueError("delivery archive index is invalid")
    if not any(item.get("archive_id") == decision.archive_id for item in entries):
        entries.append(
            {
                "archive_id": decision.archive_id,
                "package_sha256": decision.package_sha256,
                "relative_path": decision.archive.relative_path if decision.archive else None,
                "signed_by": list(decision.signed_by),
                "archived_at": decision.generated_at.isoformat(),
            }
        )
    temporary = target.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, target)


def _quality_markdown(report: QualityReportPayload) -> str:
    lines = ["# Quality Report", ""]
    for item in report.checks:
        lines.append(f"- [{'x' if item.passed else ' '}] {item.code}")
    if report.missing_evidence:
        lines.append(f"- Missing evidence count: {len(report.missing_evidence)}")
    lines.append(f"- Package SHA-256: `{report.package_sha256}`")
    return "\n".join(lines) + "\n"


def _probe_package_video(package: Path, attempt_root: Path) -> MediaProbe:
    try:
        with zipfile.ZipFile(package) as archive:
            candidates = [
                item
                for item in archive.infolist()
                if not item.is_dir()
                and Path(item.filename).suffix.casefold() == ".mp4"
                and ".." not in Path(item.filename.replace("\\", "/")).parts
            ]
            if len(candidates) != 1:
                raise ValueError("production package must contain exactly one final MP4")
            target = attempt_root / "quality-final.mp4"
            with archive.open(candidates[0]) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        raise ValueError("production package video cannot be extracted") from error
    ffprobe = os.environ.get("WORKBENCH_FFPROBE", "ffprobe")
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(target),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError("ffprobe is unavailable for delivery verification") from error
    if completed.returncode != 0:
        raise ValueError("ffprobe rejected the final MP4")
    try:
        payload = json.loads(completed.stdout)
        streams = payload["streams"]
        video = next(item for item in streams if item.get("codec_type") == "video")
        audio = next(item for item in streams if item.get("codec_type") == "audio")
        duration_ms = round(float(payload["format"]["duration"]) * 1000)
        audio_duration_ms = round(
            float(audio.get("duration", payload["format"]["duration"])) * 1000
        )
        rate_value = str(video.get("avg_frame_rate", "0/1"))
        numerator, denominator = (float(item) for item in rate_value.split("/", 1))
        return MediaProbe(
            video_codec=str(video["codec_name"]),
            audio_codec=str(audio["codec_name"]),
            width=int(video["width"]),
            height=int(video["height"]),
            fps=numerator / denominator,
            duration_ms=duration_ms,
            audio_duration_ms=audio_duration_ms,
        )
    except (KeyError, StopIteration, TypeError, ValueError, ZeroDivisionError) as error:
        raise ValueError("ffprobe response is incomplete") from error


def _single_input(job: JobEnvelope, attempt_root: Path) -> Path:
    if len(job.inputs) != 1:
        raise ValueError("P12 job requires exactly one production package input")
    reference = job.inputs[0]
    path = (attempt_root / reference.path).resolve()
    if not path.is_relative_to(attempt_root.resolve()) or not path.is_file():
        raise ValueError("delivery input escapes the attempt directory")
    if path.stat().st_size != reference.size_bytes or _sha256(path) != reference.sha256:
        raise ValueError("delivery input changed after host staging")
    return path


def _descriptor(logical_name: str, relative_path: str, path: Path) -> ArtifactDescriptor:
    return ArtifactDescriptor(
        logical_name=logical_name,
        relative_path=relative_path,
        size_bytes=path.stat().st_size,
        sha256=_sha256(path),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_manifest(path: Path, manifest: ProjectManifest) -> None:
    temporary = path.with_name(".project.json.s1.tmp")
    temporary.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


if __name__ == "__main__":
    raise SystemExit(main())
