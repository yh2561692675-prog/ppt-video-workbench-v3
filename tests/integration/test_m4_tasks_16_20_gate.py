from __future__ import annotations

import base64
import io
import wave
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from workbench.audio.models import RecognizedSegment, RecognizedWord
from workbench.domain.enums import NodeStatus
from workbench.domain.models import NarrationRecord, PageRecord
from workbench.main import create_app
from workbench.settings.secret_store import SecretProtector


class GateProtector(SecretProtector):
    def protect(self, plaintext: bytes) -> bytes:
        return base64.b64encode(plaintext[::-1])

    def unprotect(self, ciphertext: bytes) -> bytes:
        return base64.b64decode(ciphertext)[::-1]


class GateBackend:
    def transcribe(self, _: Path, **__: object) -> tuple[Iterable[RecognizedSegment], str]:
        words = [
            RecognizedWord("第一页旁白", 0.0, 0.8, 0.99),
            RecognizedWord("第二页旁白", 1.2, 1.9, 0.99),
        ]
        return (
            [
                RecognizedSegment(0.0, 0.8, "第一页旁白", [words[0]]),
                RecognizedSegment(1.2, 1.9, "第二页旁白", [words[1]]),
            ],
            "zh",
        )


def _recording() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\0\0" * 32_000)
    return buffer.getvalue()


def test_local_audio_route_import_transcribe_compare_align_and_reopen(tmp_path: Path) -> None:
    model = tmp_path / "settings" / "asr-models" / "small" / "model.bin"
    model.parent.mkdir(parents=True)
    model.write_bytes(b"fixture")
    app = create_app(
        tmp_path,
        secret_protector=GateProtector(),
        transcription_backend=GateBackend(),
    )
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "M4本地路线"}).json()["data"]
        project_id = UUID(project["id"])
        manifest = app.state.project_service.get(project_id)
        pages = []
        for order in (1, 2):
            revision = uuid4()
            pages.append(
                PageRecord(
                    id=uuid4(),
                    order=order,
                    narration=NarrationRecord(
                        id=uuid4(),
                        revision_id=revision,
                        text=f"第{order}页旁白",
                        status=NodeStatus.COMPLETED,
                        confirmed_revision_id=revision,
                    ),
                )
            )
        app.state.project_service.save(manifest.model_copy(update={"pages": pages}))

        imported = client.post(
            f"/api/projects/{project_id}/audio/import",
            files={"file": ("完整录音.wav", _recording(), "audio/wav")},
        )
        assert imported.status_code == 201
        assert client.post(f"/api/projects/{project_id}/audio/transcribe").status_code == 201
        compared = client.post(f"/api/projects/{project_id}/audio/differences/compare")
        assert compared.status_code == 200
        assert compared.json()["data"] == []
        aligned = client.post(f"/api/projects/{project_id}/audio/timeline/build")
        assert aligned.status_code == 200
        assert len(aligned.json()["data"]["segments"]) == 2

        reopened = client.get(f"/api/projects/{project_id}").json()["data"]
        assert reopened["transcript"]["words"][1]["text"] == "第二页旁白"
        assert reopened["audio_timeline"]["version"] == 1
        project_dir = tmp_path / reopened["project_dir"]
        assert all(
            (project_dir / page["audio"]["relative_path"]).exists() for page in reopened["pages"]
        )
