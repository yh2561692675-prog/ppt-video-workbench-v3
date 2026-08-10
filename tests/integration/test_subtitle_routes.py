from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from workbench.audio.models import Transcript, TranscriptWord
from workbench.domain.enums import NodeStatus
from workbench.domain.models import AudioRecord, NarrationRecord, PageRecord
from workbench.main import create_app


def _ready_project(tmp_path: Path):
    app = create_app(tmp_path)
    service = app.state.project_service
    project = service.create("字幕路由项目")
    page_id = uuid4()
    revision_id = uuid4()
    page = PageRecord(
        id=page_id,
        order=1,
        title="第一页",
        narration=NarrationRecord(
            id=uuid4(),
            revision_id=revision_id,
            confirmed_revision_id=revision_id,
            text="第一页内容。",
            status=NodeStatus.COMPLETED,
        ),
        audio=AudioRecord(
            id=uuid4(),
            status=NodeStatus.COMPLETED,
            source="heygen",
            relative_path="05_音频/heygen/page-001.wav",
            duration_ms=1_500,
            cache_key=hashlib.sha256(b"page-1").hexdigest(),
            narration_revision_id=revision_id,
            voice_id="voice-1",
        ),
    )
    project_root = tmp_path / project.project_dir
    audio_path = project_root / page.audio.relative_path
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    audio_path.write_bytes(b"fixture-audio")
    service.save(
        project.model_copy(
            update={
                "pages": [page],
                "transcript": Transcript(
                    words=[
                        TranscriptWord(text="第一", start_ms=100, end_ms=500, confidence=0.99),
                        TranscriptWord(
                            text="页内容。", start_ms=500, end_ms=1_200, confidence=0.99
                        ),
                    ],
                    detected_language="zh",
                    model="fixture",
                    device="cpu",
                    created_at=datetime.now(UTC),
                ),
            }
        )
    )
    return app, project.id


def test_subtitle_build_is_blocked_until_audio_gate_is_ready(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    project = app.state.project_service.create("尚未配音")

    with TestClient(app) as client:
        response = client.post(f"/api/projects/{project.id}/subtitles/build")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "audio_gate_blocked"


def test_subtitle_build_persists_json_and_srt_and_is_idempotent(tmp_path: Path) -> None:
    app, project_id = _ready_project(tmp_path)

    with TestClient(app) as client:
        first = client.post(f"/api/projects/{project_id}/subtitles/build")
        second = client.post(f"/api/projects/{project_id}/subtitles/build")
        fetched = client.get(f"/api/projects/{project_id}/subtitles")

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["data"] == second.json()["data"]
    assert fetched.status_code == 200
    assert fetched.json()["data"] == first.json()["data"]

    project = app.state.project_service.get(project_id)
    root = tmp_path / project.project_dir
    assert (root / "06_字幕/字幕时间轴.json").is_file()
    assert (root / "06_字幕/字幕.srt").read_text(encoding="utf-8").startswith("1\n00:00:00,100")
