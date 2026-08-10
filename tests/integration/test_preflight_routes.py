from __future__ import annotations

import hashlib
import io
import json
import wave
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
from workbench.domain.audio import AudioTimeline, AudioTimelineSegment, SubtitleArtifact
from workbench.domain.enums import NodeStatus
from workbench.domain.extraction import PageExtraction
from workbench.domain.models import AudioRecord, NarrationRecord, PageRecord
from workbench.main import create_app

RUNTIME = {"python": "3.12", "node": "22", "ffmpeg": "ffmpeg", "ffprobe": "ffprobe"}


def _wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\0\0" * 16_000)
    return buffer.getvalue()


def _ready_app(tmp_path: Path, *, ocr_confirmation: bool) -> tuple[object, object]:
    app = create_app(tmp_path, preflight_runtime_probe=lambda: RUNTIME)
    service = app.state.project_service
    project = service.create("M6预检路由")
    root = tmp_path / project.project_dir
    page_id = uuid4()
    revision_id = uuid4()
    preview = root / "02_页面预览" / "page-0001.png"
    preview.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1920, 1080), (10, 30, 60)).save(preview)
    audio = root / "05_音频" / "page-0001.wav"
    audio.parent.mkdir(parents=True, exist_ok=True)
    audio.write_bytes(_wav())
    timeline_payload = {
        "version": 1,
        "duration_ms": 1_000,
        "cues": [
            {
                "id": str(uuid4()),
                "page_id": str(page_id),
                "page_order": 1,
                "start_ms": 100,
                "end_ms": 800,
                "text": "第一页内容",
                "source_word_indexes": [0],
            }
        ],
    }
    timeline = root / "06_字幕" / "字幕时间轴.json"
    srt = root / "06_字幕" / "字幕.srt"
    timeline.parent.mkdir(parents=True, exist_ok=True)
    timeline.write_text(json.dumps(timeline_payload, ensure_ascii=False), encoding="utf-8")
    srt.write_text("1\n00:00:00,100 --> 00:00:00,800\n第一页内容\n", encoding="utf-8")
    service.save(
        project.model_copy(
            update={
                "pages": [
                    PageRecord(
                        id=page_id,
                        order=1,
                        title="第一页",
                        narration=NarrationRecord(
                            id=uuid4(),
                            revision_id=revision_id,
                            confirmed_revision_id=revision_id,
                            text="第一页内容",
                            status=NodeStatus.COMPLETED,
                        ),
                        audio=AudioRecord(
                            id=uuid4(),
                            status=NodeStatus.COMPLETED,
                            source="local",
                            relative_path="05_音频/page-0001.wav",
                            duration_ms=1_000,
                            cache_key="fixture-audio-page-1",
                            narration_revision_id=revision_id,
                        ),
                    )
                ],
                "page_extractions": [
                    PageExtraction(
                        id=uuid4(),
                        order=1,
                        text="第一页内容",
                        preview_path=preview,
                        width=1920,
                        height=1080,
                        needs_confirmation=ocr_confirmation,
                        extraction_method="image",
                        source_ref="fixture",
                    )
                ],
                "subtitle_artifact": SubtitleArtifact(
                    timeline_relative_path="06_字幕/字幕时间轴.json",
                    srt_relative_path="06_字幕/字幕.srt",
                    timeline_sha256=hashlib.sha256(timeline.read_bytes()).hexdigest(),
                    srt_sha256=hashlib.sha256(srt.read_bytes()).hexdigest(),
                ),
                "transcript": None,
                "audio_timeline": AudioTimeline(
                    id=uuid4(),
                    duration_ms=1_000,
                    segments=[
                        AudioTimelineSegment(
                            page_id=page_id,
                            start_ms=0,
                            end_ms=1_000,
                        )
                    ],
                ),
            }
        )
    )
    return app, service.get(project.id)


def test_blocking_preflight_issue_prevents_direct_http_render(tmp_path: Path) -> None:
    app = create_app(tmp_path, preflight_runtime_probe=lambda: RUNTIME)
    project = app.state.project_service.create("阻断项目")

    with TestClient(app) as client:
        report = client.post(f"/api/projects/{project.id}/preflight")
        render = client.post(f"/api/projects/{project.id}/render")

    assert report.status_code == 200
    assert report.json()["data"]["allowed"] is False
    assert render.status_code == 409
    assert render.json()["error"]["code"] == "preflight_blocked"


def test_confirmation_issue_requires_audited_confirmation_before_render(tmp_path: Path) -> None:
    app, project = _ready_app(tmp_path, ocr_confirmation=True)

    with TestClient(app) as client:
        first = client.post(f"/api/projects/{project.id}/preflight")
        issue = next(
            item
            for item in first.json()["data"]["issues"]
            if item["code"] == "ocr_needs_confirmation"
        )
        blocked = client.post(f"/api/projects/{project.id}/render")
        confirmed = client.post(
            f"/api/projects/{project.id}/issues/{issue['issue_id']}/confirm",
            json={"actor": "测试规划师", "note": "已复核页面文字，可以继续"},
        )
        report = client.get(f"/api/projects/{project.id}/preflight")
        markdown = client.get(f"/api/projects/{project.id}/preflight/report?format=markdown")

    assert first.status_code == 200
    assert blocked.status_code == 409
    assert confirmed.status_code == 200
    assert report.json()["data"]["allowed"] is True
    assert "测试规划师" in markdown.text
    assert "已复核页面文字，可以继续" in markdown.text


def test_new_preflight_replaces_old_report_after_project_input_changes(tmp_path: Path) -> None:
    app, project = _ready_app(tmp_path, ocr_confirmation=False)

    with TestClient(app) as client:
        first = client.post(f"/api/projects/{project.id}/preflight").json()["data"]
        changed = app.state.project_service.get(project.id)
        changed.pages[0].title = "修改后的标题"
        app.state.project_service.save(changed)
        second = client.post(f"/api/projects/{project.id}/preflight").json()["data"]

    assert second["id"] != first["id"]
    assert second["input_fingerprint"] != first["input_fingerprint"]
    assert len(app.state.project_service.get(project.id).preflight_history) == 2
