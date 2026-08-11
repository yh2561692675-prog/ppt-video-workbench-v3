from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import wave
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from docx import Document
from peripheral_contracts import ArtifactRef, JobEnvelope, JobResult
from workbench.domain.models import ProjectManifest


@pytest.mark.parametrize(
    ("module", "job_type"),
    [
        ("p03_material", "material.ingest"),
        ("p04_extract", "document.extract"),
        ("p05_match", "content.match"),
        ("p06_narration", "narration.import"),
        ("p07_audio", "audio.align"),
        ("p08_subtitle", "subtitle.build"),
        ("p09_effects", "effect.plan"),
        ("p10_preflight", "preflight.run"),
        ("p11_render", "package.build"),
        ("p12_delivery", "delivery.archive"),
    ],
)
def test_s1_module_entrypoint_produces_contract(tmp_path: Path, module: str, job_type: str) -> None:
    parameters = {"project_revision": 1}
    inputs = ()
    project_id = uuid4()
    if module == "p03_material":
        parameters["files"] = [
            {
                "name": "sample.pdf",
                "content_base64": base64.b64encode(b"%PDF-1.7\n").decode(),
            }
        ]
    if module == "p04_extract":
        document = Document()
        document.add_paragraph("smoke")
        from io import BytesIO

        buffer = BytesIO()
        document.save(buffer)
        parameters["files"] = [
            {
                "name": "sample.docx",
                "content_base64": base64.b64encode(buffer.getvalue()).decode(),
            }
        ]
    if module == "p05_match":
        page_id = str(uuid4())
        parameters.update(
            {
                "outline": {
                    "source_name": "outline",
                    "blocks": [
                        {
                            "kind": "heading",
                            "order": 1,
                            "level": 1,
                            "text": "Title",
                            "source_ref": "p1",
                        }
                    ],
                },
                "pages": [
                    {
                        "id": page_id,
                        "order": 1,
                        "title": "Title",
                        "text": "Title",
                        "spans": [],
                        "hidden": False,
                        "rotation": 0,
                        "needs_confirmation": False,
                        "extraction_method": "pptx",
                        "source_ref": "slide:1",
                    }
                ],
            }
        )
    if module == "p06_narration":
        parameters["assignments"] = [
            {
                "page_id": str(uuid4()),
                "expected_revision_id": None,
                "expected_version": 0,
                "text": "smoke narration",
                "author": "test",
            }
        ]
    if module == "p07_audio":
        page_id = uuid4()
        revision_id = uuid4()
        audio = tmp_path / "smoke.wav"
        with wave.open(str(audio), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16_000)
            output.writeframes(b"\0\0" * 16_000)
        digest = hashlib.sha256(audio.read_bytes()).hexdigest()
        inputs = (
            ArtifactRef(
                artifact_id=uuid4(),
                kind="wav",
                path="smoke.wav",
                size_bytes=audio.stat().st_size,
                sha256=digest,
            ),
        )
        parameters.update(
            {
                "existing_route": "local",
                "audio_import": {
                    "id": str(uuid4()),
                    "original_relative_path": "smoke.wav",
                    "normalized_relative_path": "05_音频/规范化/smoke.wav",
                    "duration_ms": 1000,
                    "sample_rate": 16000,
                    "channels": 1,
                    "sha256": digest,
                    "peak_dbfs": -96,
                    "silence_ratio": 1,
                    "silence_intervals_ms": [[0, 1000]],
                    "needs_confirmation": True,
                    "imported_at": datetime.now(UTC).isoformat(),
                },
                "transcript": {
                    "segments": [],
                    "words": [{"text": "hello", "start_ms": 100, "end_ms": 800, "confidence": 1}],
                    "detected_language": "en",
                    "model": "fake",
                    "device": "cpu",
                    "created_at": datetime.now(UTC).isoformat(),
                },
                "narrations": [
                    {
                        "page_id": str(page_id),
                        "page_order": 1,
                        "revision_id": str(revision_id),
                        "confirmed_revision_id": str(revision_id),
                        "text": "hello",
                    }
                ],
            }
        )
    if module == "p08_subtitle":
        page_id = str(uuid4())
        revision_id = str(uuid4())
        parameters.update(
            {
                "route": "local",
                "duration_ms": 1000,
                "pages": [
                    {
                        "page_id": page_id,
                        "page_order": 1,
                        "start_ms": 0,
                        "end_ms": 1000,
                        "narration_revision_id": revision_id,
                        "audio_narration_revision_id": revision_id,
                        "narration_text": "hello",
                    }
                ],
                "words": [{"text": "hello", "start_ms": 100, "end_ms": 500, "confidence": 1.0}],
            }
        )
    if module == "p09_effects":
        parameters.update({"page_id": "p1", "duration_ms": 1000, "title": "Count 1", "text": "1"})
    if module == "p10_preflight":
        project = ProjectManifest(
            id=project_id,
            name="smoke",
            project_dir="smoke",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        parameters["project_manifest"] = project.model_dump(mode="json")
    if module == "p11_render":
        source = tmp_path / "final.mp4"
        source.write_bytes(b"smoke video")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        inputs = (
            ArtifactRef(
                artifact_id=uuid4(),
                kind="mp4",
                path="final.mp4",
                size_bytes=source.stat().st_size,
                sha256=digest,
            ),
        )
        parameters.update(
            {
                "preflight_report": {
                    "project_id": str(project_id),
                    "input_fingerprint": "a" * 64,
                    "allowed": True,
                },
                "package_relative_paths": ["最终视频.mp4"],
                "duration_ms": 1000,
                "width": 1920,
                "height": 1080,
                "video_codec": "h264",
                "audio_codec": "aac",
            }
        )
    if module == "p12_delivery":
        source = tmp_path / "production-package.zip"
        source.write_bytes(b"smoke package")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        inputs = (
            ArtifactRef(
                artifact_id=uuid4(),
                kind="zip",
                path="production-package.zip",
                size_bytes=source.stat().st_size,
                sha256=digest,
            ),
        )
        artifact = {
            "logical_name": "quality-report-json",
            "relative_path": "quality-report.json",
            "size_bytes": 1,
            "sha256": "0" * 64,
        }
        parameters.update(
            {
                "quality_report": {
                    "automated_passed": True,
                    "checks": [{"code": "smoke", "passed": True}],
                    "package_sha256": digest,
                    "generated_at": datetime.now(UTC).isoformat(),
                    "artifacts": [
                        artifact,
                        {
                            **artifact,
                            "logical_name": "quality-report-md",
                            "relative_path": "quality-report.md",
                        },
                    ],
                }
            }
        )
    job = JobEnvelope(
        schema_version="1.0",
        job_id=uuid4(),
        project_id=project_id,
        job_type=job_type,
        requested_by="test",
        idempotency_key=uuid4().hex,
        inputs=inputs,
        parameters=parameters,
        created_at=datetime.now(UTC),
    )
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    # Windows PowerShell commonly emits UTF-8 with a BOM; every bundled module
    # entrypoint must accept that request form.
    request.write_bytes(b"\xef\xbb\xbf" + job.model_dump_json().encode("utf-8"))
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(("apps/api/src", "peripheral-platform/src"))
    completed = subprocess.run(
        [
            str(Path(".venv/Scripts/python.exe")),
            "-m",
            f"workbench.business_modules.{module}",
            "--request",
            str(request),
            "--result",
            str(result),
        ],
        cwd=Path.cwd(),
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    parsed = JobResult.model_validate_json(result.read_text(encoding="utf-8"))
    assert parsed.outcome == "succeeded"
