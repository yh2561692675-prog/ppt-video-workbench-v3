from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from peripheral_contracts import ArtifactRef, JobEnvelope
from workbench.business_modules.p11_render.runner import _handle, project_package_manifest
from workbench.domain.issues import PreflightReport
from workbench.domain.models import ProjectManifest


def test_p11_builds_deterministic_package_and_projects_export_record(tmp_path: Path) -> None:
    project_id = uuid4()
    report = PreflightReport(
        project_id=project_id,
        input_fingerprint="a" * 64,
        allowed=True,
    )
    manifest = ProjectManifest(
        id=project_id,
        name="demo",
        project_dir="demo",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        preflight_report=report,
    )
    (tmp_path / "project.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    source = tmp_path / "final.mp4"
    source.write_bytes(b"video content")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    job = JobEnvelope(
        schema_version="1.0",
        job_id=uuid4(),
        project_id=project_id,
        job_type="package.build",
        requested_by="test",
        idempotency_key=uuid4().hex,
        inputs=(
            ArtifactRef(
                artifact_id=uuid4(),
                kind="mp4",
                path="final.mp4",
                size_bytes=source.stat().st_size,
                sha256=digest,
            ),
        ),
        parameters={
            "project_revision": 1,
            "preflight_report": report.model_dump(mode="json"),
            "package_relative_paths": ["最终视频.mp4"],
            "duration_ms": 1000,
            "width": 1920,
            "height": 1080,
            "video_codec": "h264",
            "audio_codec": "aac",
        },
        created_at=datetime.now(UTC),
    )

    first = _handle(job, tmp_path)
    first_bytes = first.artifacts[0].path.read_bytes()
    first.artifacts[0].path.unlink()
    second = _handle(job, tmp_path)
    project_package_manifest(second.business_result, tmp_path)

    updated = ProjectManifest.model_validate_json(
        (tmp_path / "project.json").read_text(encoding="utf-8")
    )
    assert second.artifacts[0].path.read_bytes() == first_bytes
    assert updated.video_export is not None
    assert updated.video_export.package_relative_path == "08_输出/制作包.zip"
    assert updated.video_export.artifact_count == 2
