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
from uuid import uuid5

from peripheral_contracts import BusinessResultManifest, ErrorCategory, JobEnvelope

from workbench.business_modules.p11_render.models import (
    ArtifactDescriptor,
    PackageBuildParameters,
    PackageFile,
    PackageManifestPayload,
    PageSegment,
    PageSegmentsPayload,
    VideoAssembleParameters,
    VideoAssemblePayload,
    VideoRenderParameters,
)
from workbench.business_modules.runtime import (
    BusinessExecution,
    BusinessModuleError,
    StagedArtifact,
    business_input_fingerprint,
    business_parameters,
    execute_business_handler,
    project_revision,
)
from workbench.domain.enums import NodeStatus
from workbench.domain.models import AuditEvent, ProjectManifest, RenderRecord, VideoExportRecord
from workbench.video.render_service import RenderError, VideoRenderService


def build_package_manifest(root: Path, relative_paths: list[str]) -> dict[str, Any]:
    resolved_root = root.resolve()
    files: list[dict[str, Any]] = []
    for relative in sorted(relative_paths):
        target = (resolved_root / relative).resolve()
        if not target.is_relative_to(resolved_root):
            raise ValueError("package file escapes project directory")
        if target.is_symlink() or not target.is_file():
            raise ValueError("package file must be a regular file")
        files.append(
            {
                "relative_path": target.relative_to(resolved_root).as_posix(),
                "size_bytes": target.stat().st_size,
                "sha256": _sha256(target),
            }
        )
    return {"files": files, "file_count": len(files)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    job = JobEnvelope.model_validate_json(args.request.read_text(encoding="utf-8-sig"))
    execution = execute_business_handler(job, args.result.parent, args.result, "P11", _handle)
    return 0 if execution.outcome == "succeeded" else 1


def _handle(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    try:
        if job.job_type == "video.render":
            return _render(job, attempt_root)
        if job.job_type == "video.assemble":
            return _assemble(job, attempt_root)
        if job.job_type == "package.build":
            return _package(job, attempt_root)
    except ValueError as error:
        if "PREFLIGHT_BLOCKED" in str(error):
            raise BusinessModuleError(
                str(error),
                category=ErrorCategory.QA,
                code="PREFLIGHT_BLOCKED",
                retryable=False,
            ) from error
        raise
    raise ValueError(f"unsupported P11 job type: {job.job_type}")


def _render(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    parameters = VideoRenderParameters.model_validate(business_parameters(job))
    if parameters.preflight_report.project_id != job.project_id:
        raise ValueError("preflight report project identity mismatch")
    if len(parameters.input_relative_paths) != len(job.inputs):
        raise ValueError("input_relative_paths must match staged inputs")
    project_root = attempt_root / "recovery" / "render-project"
    _stage_snapshot_inputs(job, attempt_root, project_root, parameters.input_relative_paths)
    try:
        rendered = VideoRenderService(project_root).render_pages(parameters.props)
    except RenderError as error:
        raise BusinessModuleError(
            str(error),
            category=ErrorCategory.PROCESSING,
            code="PAGE_RENDER_FAILED",
            retryable=True,
        ) from error
    segments: list[PageSegment] = []
    artifacts: list[StagedArtifact] = []
    by_order = {page.page_order: page for page in parameters.props.pages}
    for item in rendered:
        page = by_order[item.page_order]
        logical_name = f"page-segment-{item.page_order:04d}"
        relative_path = f"07_视频/segments/page-{item.page_order:04d}.mp4"
        descriptor = _descriptor(logical_name, relative_path, item.path)
        segments.append(
            PageSegment(
                **descriptor.model_dump(),
                page_id=page.page_id,
                page_order=item.page_order,
                cache_key=item.cache_key,
                cached=item.cached,
            )
        )
        artifacts.append(StagedArtifact(logical_name, "mp4", item.path))
    payload = PageSegmentsPayload(
        generated_at=job.created_at,
        preflight_fingerprint=parameters.preflight_report.input_fingerprint,
        segments=tuple(segments),
    )
    return _execution(job, "page_segments", payload.model_dump(mode="json"), tuple(artifacts))


def _assemble(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    parameters = VideoAssembleParameters.model_validate(business_parameters(job))
    if parameters.preflight_report.project_id != job.project_id:
        raise ValueError("preflight report project identity mismatch")
    if len(job.inputs) != parameters.segment_count * 2:
        raise ValueError("video.assemble requires matching segment and page-audio inputs")
    segments = [_input_path(job, attempt_root, index) for index in range(parameters.segment_count)]
    audios = [
        _input_path(job, attempt_root, parameters.segment_count + index)
        for index in range(parameters.segment_count)
    ]
    ffmpeg = os.environ.get("WORKBENCH_FFMPEG", "ffmpeg")
    muxed_dir = attempt_root / "muxed"
    muxed_dir.mkdir(parents=True, exist_ok=True)
    muxed: list[Path] = []
    for index, (segment, audio) in enumerate(zip(segments, audios, strict=True), start=1):
        target = muxed_dir / f"page-{index:04d}.mp4"
        _run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(segment),
                "-i",
                str(audio),
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                "-shortest",
                str(target),
            ],
            muxed_dir,
        )
        muxed.append(target)
    concat = attempt_root / "segments.txt"
    concat.write_text(
        "".join(f"file '{item.as_posix().replace("'", "'\\''")}'\n" for item in muxed),
        encoding="utf-8",
    )
    final = attempt_root / "final.mp4"
    _run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat),
            "-c",
            "copy",
            str(final),
        ],
        attempt_root,
    )
    probe = _probe_final(final)
    if (
        probe["video_codec"] != "h264"
        or probe["audio_codec"] != "aac"
        or probe["width"] != parameters.props.width
        or probe["height"] != parameters.props.height
        or abs(float(probe["fps"]) - parameters.props.fps) > 0.01
        or abs(int(probe["duration_ms"]) - parameters.props.duration_ms) > 150
    ):
        raise BusinessModuleError(
            "assembled video does not satisfy the render contract",
            category=ErrorCategory.QA,
            code="MEDIA_VALIDATION_FAILED",
            retryable=False,
        )
    descriptor = _descriptor("final-video", "08_输出/最终视频.mp4", final)
    payload = VideoAssemblePayload(
        generated_at=job.created_at,
        preflight_fingerprint=parameters.preflight_report.input_fingerprint,
        video=descriptor,
        duration_ms=int(probe["duration_ms"]),
        width=int(probe["width"]),
        height=int(probe["height"]),
        video_codec=str(probe["video_codec"]),
        audio_codec=str(probe["audio_codec"]),
    )
    return _execution(
        job,
        "video_assembled",
        payload.model_dump(mode="json"),
        (StagedArtifact("final-video", "mp4", final),),
    )


def _package(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    parameters = PackageBuildParameters.model_validate(business_parameters(job))
    if parameters.preflight_report.project_id != job.project_id:
        raise ValueError("preflight report project identity mismatch")
    if len(parameters.package_relative_paths) != len(job.inputs):
        raise ValueError("package_relative_paths must match staged inputs")
    package_root = attempt_root / "package"
    files: list[PackageFile] = []
    for index, relative in enumerate(parameters.package_relative_paths):
        safe = _safe_relative(relative)
        source = _input_path(job, attempt_root, index)
        target = package_root / safe
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        files.append(
            PackageFile(
                relative_path=safe.as_posix(),
                size_bytes=target.stat().st_size,
                sha256=_sha256(target),
            )
        )
    manifest_path = package_root / "制作包清单.json"
    manifest_path.write_text(
        json.dumps(
            {"version": 1, "files": [item.model_dump(mode="json") for item in files]},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    files.append(
        PackageFile(
            relative_path="制作包清单.json",
            size_bytes=manifest_path.stat().st_size,
            sha256=_sha256(manifest_path),
        )
    )
    archive = attempt_root / "production-package.zip"
    _write_deterministic_zip(package_root, archive)
    descriptor = _descriptor("production-package", "08_输出/制作包.zip", archive)
    payload = PackageManifestPayload(
        generated_at=job.created_at,
        preflight_fingerprint=parameters.preflight_report.input_fingerprint,
        files=tuple(files),
        file_count=len(files),
        package=descriptor,
        duration_ms=parameters.duration_ms,
        width=parameters.width,
        height=parameters.height,
        video_codec=parameters.video_codec,
        audio_codec=parameters.audio_codec,
    )
    return _execution(
        job,
        "package_manifest",
        payload.model_dump(mode="json"),
        (StagedArtifact("production-package", "zip", archive),),
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
            module_id="P11",
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


def project_page_segments(result: BusinessResultManifest, project_dir: Path) -> None:
    payload = PageSegmentsPayload.model_validate(result.payload)
    manifest_path = project_dir / "project.json"
    manifest = _manifest_with_gate(manifest_path, payload.preflight_fingerprint)
    pages = {page.id: page for page in manifest.pages}
    for segment in payload.segments:
        page = pages.get(segment.page_id)
        if page is None:
            raise ValueError("render segment targets an unknown page")
        pages[segment.page_id] = page.model_copy(
            update={
                "render": RenderRecord(
                    id=uuid5(segment.page_id, f"P11:{segment.cache_key}"),
                    status=NodeStatus.COMPLETED,
                    relative_path=segment.relative_path,
                )
            }
        )
    updated = manifest.model_copy(
        update={
            "pages": sorted(pages.values(), key=lambda page: page.order),
            "video_export": None,
            "audit_log": [
                *manifest.audit_log,
                AuditEvent(
                    action="page_segments_projected",
                    occurred_at=payload.generated_at,
                    details={"page_ids": [str(item.page_id) for item in payload.segments]},
                ),
            ],
        }
    )
    _write_manifest(manifest_path, updated)


def project_video_assembled(result: BusinessResultManifest, project_dir: Path) -> None:
    payload = VideoAssemblePayload.model_validate(result.payload)
    manifest_path = project_dir / "project.json"
    manifest = _manifest_with_gate(manifest_path, payload.preflight_fingerprint)
    updated = manifest.model_copy(
        update={
            "video_export": VideoExportRecord(
                id=uuid5(manifest.id, f"P11:assemble:{result.cache_key}"),
                status=NodeStatus.COMPLETED,
                mp4_relative_path=payload.video.relative_path,
                duration_ms=payload.duration_ms,
                artifact_count=1,
                exported_at=payload.generated_at,
            )
        }
    )
    _write_manifest(manifest_path, updated)


def project_package_manifest(result: BusinessResultManifest, project_dir: Path) -> None:
    payload = PackageManifestPayload.model_validate(result.payload)
    manifest_path = project_dir / "project.json"
    manifest = _manifest_with_gate(manifest_path, payload.preflight_fingerprint)
    current = manifest.video_export
    updated = manifest.model_copy(
        update={
            "video_export": VideoExportRecord(
                id=current.id if current else uuid5(manifest.id, f"P11:package:{result.cache_key}"),
                status=NodeStatus.COMPLETED,
                mp4_relative_path=current.mp4_relative_path if current else None,
                package_relative_path=payload.package.relative_path,
                duration_ms=payload.duration_ms,
                artifact_count=payload.file_count,
                exported_at=payload.generated_at,
            ),
            "audit_log": [
                *manifest.audit_log,
                AuditEvent(
                    action="production_package_projected",
                    occurred_at=payload.generated_at,
                    details={
                        "file_count": payload.file_count,
                        "package_sha256": payload.package.sha256,
                    },
                ),
            ],
        }
    )
    _write_manifest(manifest_path, updated)


def _manifest_with_gate(path: Path, fingerprint: str) -> ProjectManifest:
    manifest = ProjectManifest.model_validate_json(path.read_text(encoding="utf-8"))
    report = manifest.preflight_report
    if report is None or not report.allowed or report.input_fingerprint != fingerprint:
        raise ValueError("PREFLIGHT_BLOCKED: current P10 report is missing, stale, or blocking")
    return manifest


def _stage_snapshot_inputs(
    job: JobEnvelope,
    attempt_root: Path,
    project_root: Path,
    relative_paths: tuple[str, ...],
) -> None:
    for index, relative in enumerate(relative_paths):
        source = _input_path(job, attempt_root, index)
        target = project_root / _safe_relative(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def _input_path(job: JobEnvelope, attempt_root: Path, index: int) -> Path:
    reference = job.inputs[index]
    path = (attempt_root / reference.path).resolve()
    if not path.is_relative_to(attempt_root.resolve()) or not path.is_file():
        raise ValueError("render input escapes the attempt directory")
    if path.stat().st_size != reference.size_bytes or _sha256(path) != reference.sha256:
        raise ValueError("render input changed after host staging")
    return path


def _safe_relative(value: str) -> Path:
    path = Path(value.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ValueError("package path is unsafe")
    return path


def _descriptor(logical_name: str, relative_path: str, path: Path) -> ArtifactDescriptor:
    return ArtifactDescriptor(
        logical_name=logical_name,
        relative_path=relative_path,
        size_bytes=path.stat().st_size,
        sha256=_sha256(path),
    )


def _run(command: list[str], cwd: Path) -> None:
    completed = subprocess.run(command, cwd=cwd, capture_output=True, timeout=86_400)
    if completed.returncode != 0:
        raise BusinessModuleError(
            "FFmpeg assembly failed",
            category=ErrorCategory.PROCESSING,
            code="FFMPEG_ASSEMBLY_FAILED",
            retryable=True,
        )


def _probe_final(path: Path) -> dict[str, int | float | str]:
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
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if completed.returncode != 0:
            raise ValueError("ffprobe failed")
        payload = json.loads(completed.stdout)
        video = next(item for item in payload["streams"] if item.get("codec_type") == "video")
        audio = next(item for item in payload["streams"] if item.get("codec_type") == "audio")
        numerator, denominator = (
            float(item) for item in str(video.get("avg_frame_rate", "0/1")).split("/", 1)
        )
        return {
            "video_codec": str(video["codec_name"]),
            "audio_codec": str(audio["codec_name"]),
            "width": int(video["width"]),
            "height": int(video["height"]),
            "fps": numerator / denominator,
            "duration_ms": round(float(payload["format"]["duration"]) * 1000),
        }
    except (
        OSError,
        subprocess.TimeoutExpired,
        KeyError,
        StopIteration,
        TypeError,
        ValueError,
        ZeroDivisionError,
    ) as error:
        raise BusinessModuleError(
            "assembled video could not be probed",
            category=ErrorCategory.QA,
            code="MEDIA_PROBE_FAILED",
            retryable=False,
        ) from error


def _write_deterministic_zip(root: Path, target: Path) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
            if path.is_symlink() or not path.is_file():
                continue
            info = zipfile.ZipInfo(path.relative_to(root).as_posix(), (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())


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
