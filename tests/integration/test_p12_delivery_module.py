from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from peripheral_contracts import ArtifactRef, JobEnvelope
from workbench.business_modules.p12_delivery.runner import (
    _handle,
    project_delivery_decision,
)
from workbench.domain.models import ProjectManifest


def _artifact(path: Path) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=uuid4(),
        kind="zip",
        path=path.name,
        size_bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def test_p12_quality_then_signed_delivery_creates_immutable_archive_index(
    tmp_path: Path, monkeypatch
) -> None:
    from workbench.business_modules.p12_delivery import runner
    from workbench.business_modules.p12_delivery.models import MediaProbe

    project_id = uuid4()
    package = tmp_path / "package.zip"
    video = b"fake h264/aac payload"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("最终视频.mp4", video)
    package_sha = hashlib.sha256(package.read_bytes()).hexdigest()
    manifest_payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "preflight_fingerprint": "a" * 64,
        "files": [
            {
                "relative_path": "最终视频.mp4",
                "size_bytes": len(video),
                "sha256": hashlib.sha256(video).hexdigest(),
            }
        ],
        "file_count": 1,
        "package": {
            "logical_name": "production-package",
            "relative_path": "08_输出/制作包.zip",
            "size_bytes": package.stat().st_size,
            "sha256": package_sha,
        },
        "duration_ms": 1000,
        "width": 1920,
        "height": 1080,
        "video_codec": "h264",
        "audio_codec": "aac",
    }
    monkeypatch.setattr(
        runner,
        "_probe_package_video",
        lambda *_: MediaProbe(
            video_codec="h264",
            audio_codec="aac",
            width=1920,
            height=1080,
            fps=30,
            duration_ms=1000,
            audio_duration_ms=1000,
        ),
    )
    quality_job = JobEnvelope(
        schema_version="1.0",
        job_id=uuid4(),
        project_id=project_id,
        job_type="quality.verify",
        requested_by="test",
        idempotency_key=uuid4().hex,
        inputs=(_artifact(package),),
        parameters={
            "project_revision": 1,
            "package_manifest": manifest_payload,
            "policy": {
                "required_evidence": ["windows_real_machine"],
                "required_signers": ["reviewer"],
            },
            "evidence": ["windows_real_machine"],
        },
        created_at=datetime.now(UTC),
    )
    quality = _handle(quality_job, tmp_path)
    assert quality.business_result.payload["automated_passed"] is True

    archive_job = JobEnvelope(
        schema_version="1.0",
        job_id=uuid4(),
        project_id=project_id,
        job_type="delivery.archive",
        requested_by="test",
        idempotency_key=uuid4().hex,
        inputs=(_artifact(package),),
        parameters={
            "project_revision": 1,
            "quality_report": quality.business_result.payload,
            "evidence": ["windows_real_machine"],
            "signatures": {"reviewer": "signed-by-reviewer"},
        },
        created_at=datetime.now(UTC),
    )
    decision = _handle(archive_job, tmp_path)
    manifest = ProjectManifest(
        id=project_id,
        name="demo",
        project_dir="demo",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    (tmp_path / "project.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    project_delivery_decision(decision.business_result, tmp_path)
    project_delivery_decision(decision.business_result, tmp_path)

    assert decision.business_result.payload["decision"] == "archived"
    index = json.loads((tmp_path / "08_输出" / "交付" / "index.json").read_text(encoding="utf-8"))
    assert [item["archive_id"] for item in index] == [
        decision.business_result.payload["archive_id"]
    ]
