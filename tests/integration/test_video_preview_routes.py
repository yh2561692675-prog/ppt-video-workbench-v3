from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from workbench.audio.models import Transcript, TranscriptWord
from workbench.domain.enums import NodeStatus
from workbench.domain.extraction import PageExtraction
from workbench.domain.models import AudioRecord, NarrationRecord, PageRecord
from workbench.main import create_app


def _video_ready_project(tmp_path: Path):
    app = create_app(tmp_path)
    service = app.state.project_service
    project = service.create("预检项目")
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
    root = tmp_path / project.project_dir
    audio = root / page.audio.relative_path
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(b"fixture-audio")
    preview = root / "02_页面预览/page-0001.png"
    preview.write_bytes(b"fixture-preview")
    extraction = PageExtraction(
        id=uuid4(),
        order=1,
        title="第一页",
        preview_path=Path("02_页面预览/page-0001.png"),
        extraction_method="image",
        source_ref="fixture",
    )
    service.save(
        project.model_copy(
            update={
                "pages": [page],
                "page_extractions": [extraction],
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


def test_video_preflight_returns_blockers_without_raising_for_incomplete_project(
    tmp_path: Path,
) -> None:
    app = create_app(tmp_path)
    project = app.state.project_service.create("未完成预检")

    with TestClient(app) as client:
        response = client.post(f"/api/projects/{project.id}/video/preflight")
        step = client.patch(f"/api/projects/{project.id}/step", json={"step": 7})

    assert response.status_code == 200
    assert response.json()["data"]["allowed"] is False
    assert response.json()["data"]["issues"][0]["code"] == "project_pages_missing"
    assert step.status_code == 409
    assert step.json()["error"]["code"] == "audio_gate_blocked"


def test_video_preflight_uses_same_props_after_subtitles_are_built(tmp_path: Path) -> None:
    app, project_id = _video_ready_project(tmp_path)

    with TestClient(app) as client:
        assert client.post(f"/api/projects/{project_id}/subtitles/build").status_code == 201
        response = client.post(
            f"/api/projects/{project_id}/video/preflight", json={"reduced_motion": True}
        )
        preview = client.get(f"/api/projects/{project_id}/video/preview")

    assert response.status_code == 200
    assert response.json()["data"]["allowed"] is True
    assert response.json()["data"]["props"]["width"] == 1920
    assert response.json()["data"]["props"]["reduced_motion"] is True
    assert response.json()["data"]["props"]["pages"][0]["page_order"] == 1
    assert response.json()["data"]["props"]["subtitle_placements"] == [
        {
            "page_id": str(response.json()["data"]["props"]["pages"][0]["page_id"]),
            "position": "bottom",
            "rect": {"x": 310.0, "y": 888.0, "width": 1300.0, "height": 96.0},
            "panel": False,
            "reason": None,
        }
    ]
    assert preview.json()["data"] == response.json()["data"]
    assert app.state.project_service.get(project_id).video_preflight is not None
    with TestClient(app) as client:
        asset = client.get(
            f"/api/projects/{project_id}/video/assets/02_%E9%A1%B5%E9%9D%A2%E9%A2%84%E8%A7%88/page-0001.png"
        )
        escaped = client.get(f"/api/projects/{project_id}/video/assets/../../workspace.db")
        assert client.patch(f"/api/projects/{project_id}/step", json={"step": 7}).status_code == 200
    assert asset.status_code == 200
    assert asset.content == b"fixture-preview"
    assert escaped.status_code == 404
