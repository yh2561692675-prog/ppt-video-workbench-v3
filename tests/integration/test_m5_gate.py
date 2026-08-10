from __future__ import annotations

import hashlib
import io
import subprocess
import wave
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image
from workbench.audio.models import Transcript, TranscriptWord
from workbench.domain.confirmation import Confirmation
from workbench.domain.enums import NodeStatus
from workbench.domain.extraction import PageExtraction
from workbench.domain.models import AudioRecord, NarrationRecord, PageRecord
from workbench.main import create_app
from workbench.video.models import ProjectVideoProps, VideoPageProps


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


def _wav(milliseconds: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\0\0" * round(16_000 * milliseconds / 1_000))
    return buffer.getvalue()


def _eight_page_project(tmp_path: Path):
    app = create_app(tmp_path, video_renderer=FixtureVideoRenderer())
    service = app.state.project_service
    project = service.create("M5 八页阶段门禁")
    root = tmp_path / project.project_dir
    pages = []
    extractions = []
    confirmations = []
    words = []
    page_ms = 250
    for order in range(1, 9):
        page_id = uuid4()
        revision_id = uuid4()
        audio_relative = f"05_音频/heygen/page-{order:04d}.wav"
        audio = root / audio_relative
        audio.parent.mkdir(parents=True, exist_ok=True)
        audio.write_bytes(_wav(page_ms))
        preview = root / f"02_页面预览/page-{order:04d}.png"
        preview.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1920, 1080), (order * 10, 30, 60)).save(preview)
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
                    relative_path=audio_relative,
                    duration_ms=page_ms,
                    cache_key=hashlib.sha256(f"page-{order}".encode()).hexdigest(),
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
                preview_path=preview,
                extraction_method="image",
                source_ref="fixture",
            )
        )
        start = (order - 1) * page_ms
        words.append(
            TranscriptWord(
                text=f"第{order}页。",
                start_ms=start + 20,
                end_ms=start + 180,
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


def test_m5_gate_runs_complete_eight_page_video_chain(tmp_path: Path) -> None:
    app, project_id = _eight_page_project(tmp_path)

    with TestClient(app) as client:
        assert client.post(f"/api/projects/{project_id}/subtitles/build").status_code == 201
        preflight = client.post(f"/api/projects/{project_id}/video/preflight")
        export = client.post(f"/api/projects/{project_id}/video/render")

    assert preflight.json()["data"]["allowed"] is True
    assert export.status_code == 201
    data = export.json()["data"]
    assert abs(data["duration_ms"] - 2_000) <= 100
    assert data["artifact_count"] >= 9
    assert app.state.project_service.get(project_id).video_export is not None
