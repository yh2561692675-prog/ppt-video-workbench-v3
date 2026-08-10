from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from workbench.audio.models import RecognizedSegment, RecognizedWord
from workbench.domain.audio import AudioDifference, AudioTimeline, AudioTimelineSegment
from workbench.domain.enums import NodeStatus
from workbench.domain.models import AudioRecord, NarrationRecord, PageRecord
from workbench.main import create_app
from workbench.settings.secret_store import SecretProtector


class RouteProtector(SecretProtector):
    def protect(self, plaintext: bytes) -> bytes:
        return plaintext[::-1]

    def unprotect(self, ciphertext: bytes) -> bytes:
        return ciphertext[::-1]


class EightPageBackend:
    def transcribe(self, _: Path, **__: object) -> tuple[list[RecognizedSegment], str]:
        words = [
            RecognizedWord(f"第{order}页旁白", float(order - 1), float(order) - 0.1, 0.99)
            for order in range(1, 9)
        ]
        return (
            [RecognizedSegment(word.start, word.end, word.text, [word]) for word in words],
            "zh",
        )


def _recording(seconds: int = 8) -> bytes:
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\0\0" * 16_000 * seconds)
    return buffer.getvalue()


def _confirmed_page(order: int, source: Literal["local", "heygen"] = "local") -> PageRecord:
    page_id = uuid4()
    revision_id = uuid4()
    voice_id = "my-voice" if source == "heygen" else None
    cache_key = hashlib.sha256(f"{revision_id}|{voice_id or 'local'}".encode()).hexdigest()
    return PageRecord(
        id=page_id,
        order=order,
        narration=NarrationRecord(
            id=uuid4(),
            revision_id=revision_id,
            confirmed_revision_id=revision_id,
            text=f"第{order}页旁白",
            status=NodeStatus.COMPLETED,
        ),
        audio=AudioRecord(
            id=uuid4(),
            status=NodeStatus.COMPLETED,
            source=source,
            relative_path=f"05_音频/{source}/page-{order:03d}.wav",
            duration_ms=800,
            cache_key=cache_key,
            narration_revision_id=revision_id,
            voice_id=voice_id,
        ),
    )


def _write_page_audio(project_root: Path, pages: list[PageRecord]) -> None:
    for page in pages:
        assert page.audio is not None and page.audio.relative_path is not None
        target = project_root / page.audio.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"fixture-audio")


def _timeline(pages: list[PageRecord]) -> AudioTimeline:
    return AudioTimeline(
        id=uuid4(),
        version=1,
        duration_ms=len(pages) * 800,
        segments=[
            AudioTimelineSegment(
                page_id=page.id,
                start_ms=index * 800,
                end_ms=(index + 1) * 800,
            )
            for index, page in enumerate(pages)
        ],
    )


def _save_ready_project(
    tmp_path: Path, *, source: Literal["local", "heygen"] = "local"
) -> tuple[object, UUID, list[PageRecord]]:
    app = create_app(tmp_path)
    service = app.state.project_service
    project = service.create("Task21 音频路线")
    pages = [_confirmed_page(order, source) for order in range(1, 9)]
    project_root = tmp_path / project.project_dir
    _write_page_audio(project_root, pages)
    service.save(
        project.model_copy(
            update={
                "pages": pages,
                "audio_timeline": _timeline(pages) if source == "local" else None,
            }
        )
    )
    return app, project.id, pages


def test_resolve_page_audio_returns_ordered_complete_local_route(tmp_path: Path) -> None:
    from workbench.audio.service import AudioService

    app, project_id, pages = _save_ready_project(tmp_path)
    manifest = app.state.project_service.get(project_id)

    resolved = AudioService(tmp_path).resolve_page_audio(manifest)

    assert [item.page_id for item in resolved] == [page.id for page in pages]
    assert [item.source for item in resolved] == ["local"] * 8
    assert all(item.duration_ms == 800 and item.path.endswith(".wav") for item in resolved)


def test_subtitle_gate_allows_complete_eight_page_local_route(tmp_path: Path) -> None:
    app, project_id, _ = _save_ready_project(tmp_path)

    with TestClient(app) as client:
        response = client.get(f"/api/projects/{project_id}/audio/gate")

    assert response.status_code == 200
    assert response.json()["data"] == {"allowed": True, "reasons": []}


def test_full_eight_page_local_route_becomes_subtitle_ready(tmp_path: Path) -> None:
    model = tmp_path / "settings" / "asr-models" / "small" / "model.bin"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"fixture")
    app = create_app(
        tmp_path,
        secret_protector=RouteProtector(),
        transcription_backend=EightPageBackend(),
    )
    with TestClient(app) as client:
        created = client.post("/api/projects", json={"name": "M4 本地八页"}).json()["data"]
        project_id = UUID(created["id"])
        manifest = app.state.project_service.get(project_id)
        pages = [_confirmed_page(order) for order in range(1, 9)]
        app.state.project_service.save(manifest.model_copy(update={"pages": pages}))

        assert (
            client.post(
                f"/api/projects/{project_id}/audio/import",
                files={"file": ("完整录音.wav", _recording(), "audio/wav")},
            ).status_code
            == 201
        )
        assert client.post(f"/api/projects/{project_id}/audio/transcribe").status_code == 201
        compared = client.post(f"/api/projects/{project_id}/audio/differences/compare")
        assert compared.json()["data"] == []
        assert client.post(f"/api/projects/{project_id}/audio/timeline/build").status_code == 200

        gate = client.get(f"/api/projects/{project_id}/audio/gate")
        assert gate.json()["data"] == {"allowed": True, "reasons": []}
        assert client.patch(f"/api/projects/{project_id}/step", json={"step": 6}).status_code == 200

    saved = app.state.project_service.get(project_id)
    assert all(
        page.audio is not None
        and page.audio.source == "local"
        and page.audio.cache_key
        and page.audio.narration_revision_id == page.narration.revision_id
        for page in saved.pages
        if page.narration is not None
    )


def test_subtitle_gate_blocks_mixed_routes_missing_audio_and_audio_reuse(tmp_path: Path) -> None:
    app, project_id, pages = _save_ready_project(tmp_path)
    manifest = app.state.project_service.get(project_id)
    mixed = pages[1].model_copy(
        update={
            "audio": pages[1].audio.model_copy(update={"source": "heygen", "voice_id": "my-voice"})
            if pages[1].audio
            else None
        }
    )
    missing = pages[2].model_copy(update={"audio": None})
    reused = pages[3].model_copy(
        update={
            "audio": pages[3].audio.model_copy(
                update={"relative_path": "05_音频/local/./page-001.wav"}
            )
            if pages[3].audio and pages[0].audio
            else None
        }
    )
    app.state.project_service.save(
        manifest.model_copy(update={"pages": [pages[0], mixed, missing, reused, *pages[4:]]})
    )

    with TestClient(app) as client:
        response = client.get(f"/api/projects/{project_id}/audio/gate")

    assert response.status_code == 200
    assert response.json()["data"]["allowed"] is False
    assert {reason["code"] for reason in response.json()["data"]["reasons"]} >= {
        "audio_route_mixed",
        "page_audio_missing",
        "page_audio_reused",
    }


def test_subtitle_gate_blocks_pending_and_severe_local_differences(tmp_path: Path) -> None:
    app, project_id, pages = _save_ready_project(tmp_path)
    manifest = app.state.project_service.get(project_id)
    pending = AudioDifference(
        id=uuid4(),
        page_id=pages[0].id,
        kind="uncertain",
        expected="课程",
        actual="科程",
        start_ms=0,
        end_ms=300,
        confidence=0.45,
    )
    severe = AudioDifference(
        id=uuid4(),
        page_id=pages[1].id,
        kind="omission",
        expected="就业方向",
        actual="",
        start_ms=800,
        end_ms=1400,
        confidence=0.99,
    )
    app.state.project_service.save(
        manifest.model_copy(update={"audio_differences": [pending, severe]})
    )

    with TestClient(app) as client:
        response = client.get(f"/api/projects/{project_id}/audio/gate")

    assert response.status_code == 200
    assert {reason["code"] for reason in response.json()["data"]["reasons"]} >= {
        "audio_difference_unconfirmed",
        "audio_difference_severe",
    }


def test_subtitle_gate_blocks_heygen_voice_change_and_stale_revision(tmp_path: Path) -> None:
    app, project_id, pages = _save_ready_project(tmp_path, source="heygen")
    manifest = app.state.project_service.get(project_id)
    changed_voice = pages[1].model_copy(
        update={
            "audio": pages[1].audio.model_copy(update={"voice_id": "other-voice"})
            if pages[1].audio
            else None
        }
    )
    stale_revision = uuid4()
    stale = pages[2].model_copy(
        update={
            "narration": pages[2].narration.model_copy(
                update={"revision_id": stale_revision, "confirmed_revision_id": stale_revision}
            )
            if pages[2].narration
            else None
        }
    )
    app.state.project_service.save(
        manifest.model_copy(update={"pages": [pages[0], changed_voice, stale, *pages[3:]]})
    )

    with TestClient(app) as client:
        response = client.get(f"/api/projects/{project_id}/audio/gate")

    assert response.status_code == 200
    assert {reason["code"] for reason in response.json()["data"]["reasons"]} >= {
        "heygen_voice_mixed",
        "page_audio_stale",
    }


def test_subtitle_gate_prevents_entering_step_six_until_audio_route_is_ready(
    tmp_path: Path,
) -> None:
    app = create_app(tmp_path)
    service = app.state.project_service
    project = service.create("字幕门禁")

    with TestClient(app) as client:
        response = client.patch(f"/api/projects/{project.id}/step", json={"step": 6})
        later = client.patch(f"/api/projects/{project.id}/step", json={"step": 7})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "audio_gate_blocked"
    assert later.status_code == 409
    assert later.json()["error"]["code"] == "audio_gate_blocked"
