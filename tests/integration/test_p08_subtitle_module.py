from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from peripheral_contracts import JobEnvelope
from workbench.business_modules.p08_subtitle.runner import (
    _handle,
    project_subtitle_timeline,
)
from workbench.domain.enums import NodeStatus
from workbench.domain.models import AudioRecord, NarrationRecord, PageRecord, ProjectManifest


def test_p08_builds_and_projects_subtitles_bound_to_current_audio_revision(
    tmp_path: Path,
) -> None:
    project_id = uuid4()
    page_id = uuid4()
    revision_id = uuid4()
    manifest = ProjectManifest(
        id=project_id,
        name="demo",
        project_dir="demo",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        pages=[
            PageRecord(
                id=page_id,
                order=1,
                narration=NarrationRecord(
                    id=revision_id,
                    revision_id=revision_id,
                    confirmed_revision_id=revision_id,
                    text="hello",
                ),
                audio=AudioRecord(
                    id=uuid4(),
                    status=NodeStatus.COMPLETED,
                    source="local",
                    relative_path="05_音频/分页面/page-001.wav",
                    duration_ms=1000,
                    cache_key="a" * 64,
                    narration_revision_id=revision_id,
                ),
            )
        ],
    )
    (tmp_path / "project.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    job = JobEnvelope(
        schema_version="1.0",
        job_id=uuid4(),
        project_id=project_id,
        job_type="subtitle.build",
        requested_by="test",
        idempotency_key=uuid4().hex,
        parameters={
            "project_revision": 1,
            "route": "local",
            "duration_ms": 1000,
            "pages": [
                {
                    "page_id": str(page_id),
                    "page_order": 1,
                    "start_ms": 0,
                    "end_ms": 1000,
                    "narration_revision_id": str(revision_id),
                    "audio_narration_revision_id": str(revision_id),
                    "narration_text": "hello",
                }
            ],
            "words": [{"text": "hello", "start_ms": 100, "end_ms": 800, "confidence": 1}],
        },
        created_at=datetime.now(UTC),
    )

    execution = _handle(job, tmp_path)
    project_subtitle_timeline(execution.business_result, tmp_path)

    updated = ProjectManifest.model_validate_json(
        (tmp_path / "project.json").read_text(encoding="utf-8")
    )
    assert updated.subtitle_artifact is not None
    assert updated.subtitle_artifact.srt_relative_path == "06_字幕/字幕.srt"
    assert len(execution.artifacts) == 2
