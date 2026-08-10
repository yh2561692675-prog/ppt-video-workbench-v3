from __future__ import annotations

import os
import base64
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from docx import Document

from peripheral_contracts import JobEnvelope, JobResult
from workbench.domain.models import ProjectManifest


@pytest.mark.parametrize(
    ("module", "job_type"),
    [("p03_material", "material.ingest"), ("p04_extract", "document.extract"),
     ("p05_match", "content.match"), ("p06_narration", "narration.generate"),
     ("p07_audio", "audio.normalize"), ("p08_subtitle", "subtitle.build"),
     ("p09_effects", "effect.plan"), ("p10_preflight", "preflight.run"),
     ("p11_render", "package.build"), ("p12_delivery", "quality.verify")],
)
def test_s1_module_entrypoint_produces_contract(tmp_path: Path, module: str, job_type: str) -> None:
    parameters = {"project_revision": 1}
    if module == "p03_material":
        parameters["files"] = [{
            "name": "sample.pdf",
            "content_base64": base64.b64encode(b"%PDF-1.7\n").decode(),
        }]
    if module == "p04_extract":
        document = Document()
        document.add_paragraph("smoke")
        from io import BytesIO

        buffer = BytesIO()
        document.save(buffer)
        parameters["files"] = [{
            "name": "sample.docx",
            "content_base64": base64.b64encode(buffer.getvalue()).decode(),
        }]
    if module == "p05_match":
        page_id = str(uuid4())
        parameters.update({
            "outline": {"source_name": "outline", "blocks": [{
                "kind": "heading", "order": 1, "level": 1, "text": "Title", "source_ref": "p1",
            }]},
            "pages": [{"id": page_id, "order": 1, "title": "Title", "text": "Title", "spans": [],
                        "hidden": False, "rotation": 0, "needs_confirmation": False,
                        "extraction_method": "pptx", "source_ref": "slide:1"}],
        })
    if module == "p07_audio":
        parameters.update({"metadata": {"duration_ms": 1000, "sample_rate": 48000, "channels": 2},
                           "pages": [{"page_id": "p1", "duration_ms": 1000}]})
    if module == "p08_subtitle":
        page_id = str(uuid4())
        parameters.update({"duration_ms": 1000,
                           "pages": [{"page_id": page_id, "page_order": 1, "start_ms": 0, "end_ms": 1000}],
                           "words": [{"text": "hello", "start_ms": 100, "end_ms": 500, "confidence": 1.0}]})
    if module == "p09_effects":
        parameters.update({"page_id": "p1", "duration_ms": 1000, "title": "Count 1", "text": "1"})
    if module == "p10_preflight":
        project = ProjectManifest(id=uuid4(), name="smoke", project_dir="smoke",
                                  created_at=datetime.now(UTC), updated_at=datetime.now(UTC))
        parameters["project_manifest"] = project.model_dump(mode="json")
    job = JobEnvelope(
        schema_version="1.0", job_id=uuid4(), project_id=uuid4(), job_type=job_type,
        requested_by="test", idempotency_key=uuid4().hex, parameters=parameters,
        created_at=datetime.now(UTC),
    )
    request = tmp_path / "request.json"
    result = tmp_path / "result.json"
    request.write_text(job.model_dump_json(), encoding="utf-8")
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(("apps/api/src", "peripheral-platform/src"))
    completed = subprocess.run(
        [str(Path(".venv/Scripts/python.exe")), "-m", f"workbench.business_modules.{module}",
         "--request", str(request), "--result", str(result)],
        cwd=Path.cwd(), env=environment, capture_output=True, text=True, timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    parsed = JobResult.model_validate_json(result.read_text(encoding="utf-8"))
    assert parsed.outcome == "succeeded"
