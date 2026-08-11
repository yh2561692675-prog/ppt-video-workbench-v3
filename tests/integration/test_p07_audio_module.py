from __future__ import annotations

import hashlib
import wave
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from peripheral_contracts import ArtifactRef, JobEnvelope
from workbench.business_modules.p07_audio.runner import _handle, project_audio_pipeline
from workbench.domain.audio import AudioImportRecord
from workbench.domain.models import NarrationRecord, PageRecord, ProjectManifest


def _wav(path: Path, duration_ms: int = 1000) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(b"\0\0" * (16_000 * duration_ms // 1000))


def test_p07_aligns_local_audio_and_projects_revision_bound_page_audio(tmp_path: Path) -> None:
    project_id = uuid4()
    page_id = uuid4()
    revision_id = uuid4()
    audio = tmp_path / "input.wav"
    _wav(audio)
    digest = hashlib.sha256(audio.read_bytes()).hexdigest()
    imported = AudioImportRecord(
        id=uuid4(),
        original_relative_path="recording.wav",
        normalized_relative_path="05_音频/规范化/audio.normalized.wav",
        duration_ms=1000,
        sample_rate=16_000,
        channels=1,
        sha256=digest,
        peak_dbfs=-96,
        silence_ratio=1,
        silence_intervals_ms=[(0, 1000)],
        needs_confirmation=True,
        imported_at=datetime.now(UTC),
    )
    job = JobEnvelope(
        schema_version="1.0",
        job_id=uuid4(),
        project_id=project_id,
        job_type="audio.align",
        requested_by="test",
        idempotency_key=uuid4().hex,
        inputs=(
            ArtifactRef(
                artifact_id=uuid4(),
                kind="wav",
                path="input.wav",
                size_bytes=audio.stat().st_size,
                sha256=digest,
            ),
        ),
        parameters={
            "project_revision": 1,
            "existing_route": "local",
            "audio_import": imported.model_dump(mode="json"),
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
        },
        created_at=datetime.now(UTC),
    )
    manifest = ProjectManifest(
        id=project_id,
        name="demo",
        project_dir="demo",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        audio_import=imported,
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
            )
        ],
    )
    (tmp_path / "project.json").write_text(manifest.model_dump_json(), encoding="utf-8")

    execution = _handle(job, tmp_path)
    project_audio_pipeline(execution.business_result, tmp_path)

    updated = ProjectManifest.model_validate_json(
        (tmp_path / "project.json").read_text(encoding="utf-8")
    )
    assert updated.audio_timeline is not None
    assert updated.pages[0].audio is not None
    assert updated.pages[0].audio.source == "local"
    assert updated.pages[0].audio.narration_revision_id == revision_id
    assert execution.artifacts[0].path.is_file()
