from __future__ import annotations

import hashlib
import io
import subprocess
import wave
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from workbench.audio.models import Transcript, TranscriptWord
from workbench.domain.confirmation import Confirmation
from workbench.domain.enums import NodeStatus
from workbench.domain.extraction import PageExtraction
from workbench.domain.models import AudioRecord, NarrationRecord, PageRecord
from workbench.main import create_app
from workbench.video.models import ProjectVideoProps, VideoPageProps
from workbench.video.render_service import RenderError


class FixtureVideoRenderer:
    def render(
        self,
        _: ProjectVideoProps,
        page: VideoPageProps,
        source: Path,
        output: Path,
    ) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-loop",
                "1",
                "-i",
                str(source),
                "-t",
                f"{(page.end_ms - page.start_ms) / 1_000:.3f}",
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(output),
            ],
            check=True,
        )


class FailingVideoRenderer:
    def render(
        self,
        _: ProjectVideoProps,
        __: VideoPageProps,
        ___: Path,
        ____: Path,
    ) -> None:
        raise RuntimeError("renderer credential=value must not leak")


def _wav(seconds: int = 1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\0\0" * 16_000 * seconds)
    return buffer.getvalue()


def _ready_project(tmp_path: Path, renderer: object | None = None):
    app = create_app(tmp_path, video_renderer=renderer or FixtureVideoRenderer())
    service = app.state.project_service
    project = service.create("两页视频导出")
    pages = []
    extractions = []
    words = []
    confirmations = []
    root = tmp_path / project.project_dir
    for order in range(1, 3):
        page_id = uuid4()
        revision_id = uuid4()
        relative_audio = f"05_音频/heygen/page-{order:04d}.wav"
        audio_path = root / relative_audio
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(_wav())
        preview_path = root / f"02_页面预览/page-{order:04d}.png"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1920, 1080), (10 * order, 30, 60)).save(preview_path)
        pages.append(
            PageRecord(
                id=page_id,
                order=order,
                title=f"第{order}页",
                narration=NarrationRecord(
                    id=uuid4(),
                    revision_id=revision_id,
                    confirmed_revision_id=revision_id,
                    text=f"第{order}页内容。",
                    status=NodeStatus.COMPLETED,
                ),
                audio=AudioRecord(
                    id=uuid4(),
                    status=NodeStatus.COMPLETED,
                    source="heygen",
                    relative_path=relative_audio,
                    duration_ms=1_000,
                    cache_key=hashlib.sha256(f"audio-{order}".encode()).hexdigest(),
                    narration_revision_id=revision_id,
                    voice_id="voice-1",
                ),
            )
        )
        confirmations.append(
            Confirmation(
                id=uuid4(),
                page_id=page_id,
                revision_id=revision_id,
                actor="fixture",
                confirmed_at=datetime.now(UTC),
            )
        )
        extractions.append(
            PageExtraction(
                id=uuid4(),
                order=order,
                title=f"第{order}页",
                preview_path=preview_path,
                extraction_method="image",
                source_ref="fixture",
            )
        )
        start = (order - 1) * 1_000
        words.append(
            TranscriptWord(
                text=f"第{order}页内容。",
                start_ms=start + 100,
                end_ms=start + 800,
                confidence=0.99,
            )
        )
    service.save(
        project.model_copy(
            update={
                "pages": pages,
                "page_extractions": extractions,
                "narration_confirmations": confirmations,
                "transcript": Transcript(
                    words=words,
                    detected_language="zh",
                    model="fixture",
                    device="cpu",
                    created_at=datetime.now(UTC),
                ),
            }
        )
    )
    return app, project.id


def test_two_page_video_export_creates_complete_production_package(tmp_path: Path) -> None:
    app, project_id = _ready_project(tmp_path)

    with TestClient(app) as client:
        assert client.post(f"/api/projects/{project_id}/subtitles/build").status_code == 201
        preflight = client.post(f"/api/projects/{project_id}/video/preflight")
        export = client.post(f"/api/projects/{project_id}/video/render")

    assert preflight.json()["data"]["allowed"] is True
    assert export.status_code == 201
    data = export.json()["data"]
    root = tmp_path / app.state.project_service.get(project_id).project_dir
    assert (root / data["mp4_relative_path"]).is_file()
    package = root / data["package_relative_path"]
    assert package.is_dir()
    expected = [
        "最终视频.mp4",
        "字幕.srt",
        "旁白确认版.docx",
        "分页音频/page-0001.wav",
        "分页音频/page-0002.wav",
        "Remotion工程/ProjectVideoProps.json",
        "预检报告.json",
        "日志清单.json",
        "制作包清单.json",
    ]
    assert all((package / relative).is_file() for relative in expected)
    assert data["width"] == 1920
    assert data["height"] == 1080
    assert data["audio_codec"] == "aac"
    assert data["video_codec"] == "h264"
    assert app.state.project_service.get(project_id).video_export is not None


def test_render_failure_returns_redacted_error_and_persists_audit_state(tmp_path: Path) -> None:
    app, project_id = _ready_project(tmp_path, renderer=FailingVideoRenderer())

    with TestClient(app) as client:
        assert client.post(f"/api/projects/{project_id}/subtitles/build").status_code == 201
        assert client.post(f"/api/projects/{project_id}/video/preflight").status_code == 200
        response = client.post(f"/api/projects/{project_id}/video/render")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "video_export_rejected"
    assert "credential=value" not in response.json()["error"]["message"]
    manifest = app.state.project_service.get(project_id)
    assert manifest.video_export is not None
    assert manifest.video_export.status == NodeStatus.FAILED
    assert manifest.audit_log[-1].action == "video_export_failed"


def test_direct_export_failure_persists_the_same_audit_state(tmp_path: Path) -> None:
    app, project_id = _ready_project(tmp_path, renderer=FailingVideoRenderer())

    with TestClient(app) as client:
        assert client.post(f"/api/projects/{project_id}/subtitles/build").status_code == 201
        assert client.post(f"/api/projects/{project_id}/video/preflight").status_code == 200

    with pytest.raises(RenderError, match="第1页渲染失败"):
        app.state.video_export_service.export(project_id)

    manifest = app.state.project_service.get(project_id)
    assert manifest.video_export is not None
    assert manifest.video_export.status == NodeStatus.FAILED
    assert manifest.audit_log[-1].action == "video_export_failed"


def test_preflight_block_does_not_create_a_failed_export_record(tmp_path: Path) -> None:
    app = create_app(tmp_path, video_renderer=FixtureVideoRenderer())
    project = app.state.project_service.create("未完成视频导出")

    with TestClient(app) as client:
        response = client.post(f"/api/projects/{project.id}/video/render")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "video_preflight_blocked"
    assert app.state.project_service.get(project.id).video_export is None
