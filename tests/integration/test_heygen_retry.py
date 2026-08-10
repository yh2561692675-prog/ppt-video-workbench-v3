from __future__ import annotations

import base64
import io
import json
import wave
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from workbench.audio.service import AudioService
from workbench.domain.enums import NodeStatus
from workbench.domain.models import NarrationRecord, PageRecord
from workbench.integrations.heygen.client import HeyGenClient, HeyGenIntegrationError
from workbench.main import create_app
from workbench.settings.heygen_store import HeyGenProfileStore
from workbench.settings.secret_store import SecretProtector


class TestProtector(SecretProtector):
    def protect(self, plaintext: bytes) -> bytes:
        return base64.b64encode(plaintext[::-1])

    def unprotect(self, ciphertext: bytes) -> bytes:
        return base64.b64decode(ciphertext)[::-1]


def test_profile_store_replaces_an_expired_key_without_creating_a_duplicate(tmp_path: Path) -> None:
    store = HeyGenProfileStore(tmp_path / "settings" / "heygen-profiles.json", TestProtector())
    created = store.save(name="旧配置", base_url="https://api.heygen.test", api_key="expired-key")

    updated = store.update(
        created.id,
        name="本人声音",
        base_url="https://api.heygen.test",
        api_key="replacement-key",
    )

    assert updated.id == created.id
    assert updated.name == "本人声音"
    assert len(store.list_profiles()) == 1
    assert store.credentials(created.id).api_key == "replacement-key"
    assert "replacement-key" not in store.path.read_text(encoding="utf-8")


def _wav_bytes() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16_000)
        handle.writeframes(b"\0\0" * 8_000)
    return buffer.getvalue()


def test_long_narration_splitter_prefers_sentence_boundaries_and_respects_limit() -> None:
    from workbench.audio.heygen_chunks import split_speech_text

    text = "甲" * 70 + "。" + "乙" * 70 + "，" + "丙" * 70 + "。"

    parts = split_speech_text(text, max_chars=120)

    assert parts == ["甲" * 70 + "。", "乙" * 70 + "，", "丙" * 70 + "。"]
    assert all(len(part) <= 120 for part in parts)


def test_long_narration_default_chunks_never_exceed_sixty_characters() -> None:
    from workbench.audio.heygen_chunks import split_speech_text

    parts = split_speech_text("甲" * 130)

    assert parts == ["甲" * 60, "甲" * 60, "甲" * 10]


def test_long_narration_concatenation_joins_normalized_wavs_without_reencoding(
    tmp_path: Path,
) -> None:
    from workbench.audio.heygen_chunks import concatenate_normalized_wavs

    first = tmp_path / "part-001.normalized.wav"
    second = tmp_path / "part-002.normalized.wav"
    first.write_bytes(_wav_bytes())
    second.write_bytes(_wav_bytes())

    result = concatenate_normalized_wavs([first, second], tmp_path / "page-003.normalized.wav")

    assert result.wav_path.exists()
    assert result.duration_ms == 1000
    with wave.open(str(result.wav_path), "rb") as merged:
        assert (
            merged.getframerate(),
            merged.getnchannels(),
            merged.getsampwidth(),
        ) == (16_000, 1, 2)
        assert merged.getnframes() == 16_000


def test_long_narration_resumes_only_the_failed_segment_and_publishes_one_page_audio(
    tmp_path: Path,
) -> None:
    from workbench.audio.heygen_chunks import split_speech_text

    narration_text = "甲" * 70 + "。" + "乙" * 70 + "。" + "丙" * 70 + "。"
    parts = split_speech_text(narration_text)
    post_counts: dict[str, int] = {}

    def transport(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v3/voices/speech":
            text = str(json.loads(request.content)["text"])
            post_counts[text] = post_counts.get(text, 0) + 1
            if text not in parts or (text == parts[1] and post_counts[text] <= 3):
                return httpx.Response(500, json={"error": {"code": "internal_error"}})
            return httpx.Response(
                200,
                json={
                    "data": {
                        "audio_url": f"https://api.heygen.test/audio/{parts.index(text)}.wav",
                        "duration": 0.5,
                        "request_id": f"request-{parts.index(text)}-{post_counts[text]}",
                    }
                },
            )
        if request.method == "GET" and request.url.path.startswith("/audio/"):
            return httpx.Response(200, content=_wav_bytes(), headers={"Content-Type": "audio/wav"})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    app = create_app(
        tmp_path,
        secret_protector=TestProtector(),
        heygen_transport=httpx.MockTransport(transport),
    )
    with TestClient(app) as api:
        project = api.post("/api/projects", json={"name": "长旁白断点续跑"}).json()["data"]
        project_id = UUID(project["id"])
        manifest = app.state.project_service.get(project_id)
        revision_id = uuid4()
        page = PageRecord(
            id=uuid4(),
            order=3,
            narration=NarrationRecord(
                id=uuid4(),
                revision_id=revision_id,
                confirmed_revision_id=revision_id,
                text=narration_text,
                status=NodeStatus.COMPLETED,
            ),
        )
        app.state.project_service.save(manifest.model_copy(update={"pages": [page]}))
        profile = api.post(
            "/api/settings/heygen-profiles",
            json={
                "name": "长旁白声音",
                "base_url": "https://api.heygen.test",
                "api_key": "hg-secret",
            },
        ).json()["data"]
        payload = {
            "profile_id": profile["id"],
            "revision_id": str(revision_id),
            "voice_id": "my-voice",
            "speed": 1.0,
        }

        failed = api.post(f"/api/projects/{project_id}/audio/heygen/{page.id}", json=payload)
        assert failed.status_code == 422
        assert app.state.project_service.get(project_id).pages[0].audio is None
        assert post_counts == {parts[0]: 1, parts[1]: 3}

        resumed = api.post(f"/api/projects/{project_id}/audio/heygen/{page.id}", json=payload)
        assert resumed.status_code == 201

    assert post_counts[parts[0]] == 1
    assert post_counts[parts[1]] == 4
    assert all(post_counts[part] == 1 for part in parts[2:])
    completed = app.state.project_service.get(project_id).pages[0].audio
    assert completed is not None
    assert completed.duration_ms == len(parts) * 500
    assert completed.relative_path == "05_音频/HeyGen/page-003.normalized.wav"
    part_state = next((tmp_path / project["project_dir"] / "05_音频/HeyGen/分段").glob("*.json"))
    state_text = part_state.read_text(encoding="utf-8")
    assert narration_text not in state_text
    assert "hg-secret" not in state_text


@pytest.mark.parametrize(
    ("status_code", "code", "expected"),
    [
        (401, "authentication_failed", "heygen_authentication_failed"),
        (402, "insufficient_credits", "heygen_quota_exhausted"),
        (429, "rate_limit_exceeded", "heygen_rate_limited"),
        (500, "internal_error", "heygen_service_error"),
    ],
)
def test_client_maps_remote_failures(status_code: int, code: str, expected: str) -> None:
    def transport(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"error": {"code": code, "message": "failed"}})

    client = HeyGenClient(transport=httpx.MockTransport(transport))
    with pytest.raises(HeyGenIntegrationError) as caught:
        client.list_voices("secret")
    assert caught.value.code == expected


def test_client_stops_after_three_timeouts() -> None:
    attempts = 0
    waits: list[float] = []

    def transport(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("timed out", request=request)

    client = HeyGenClient(
        transport=httpx.MockTransport(transport),
        retry_backoff_seconds=2,
        sleeper=waits.append,
    )
    with pytest.raises(HeyGenIntegrationError) as caught:
        client.generate_speech("secret", text="测试", voice_id="voice")
    assert caught.value.code == "heygen_timeout"
    assert attempts == 3
    assert waits == [2, 4]


def test_client_retries_two_timeouts_then_succeeds_with_exponential_backoff() -> None:
    attempts = 0
    waits: list[float] = []

    def transport(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "audio_url": "https://api.heygen.test/audio/final.wav",
                    "duration": 1.0,
                    "request_id": "request-final",
                }
            },
        )

    client = HeyGenClient(
        transport=httpx.MockTransport(transport),
        retry_backoff_seconds=2,
        sleeper=waits.append,
    )

    result = client.generate_speech("secret", text="短旁白", voice_id="voice")

    assert result.request_id == "request-final"
    assert attempts == 3
    assert waits == [2, 4]


def test_eight_pages_auto_retries_only_failed_page_and_never_regenerates_success(
    tmp_path: Path,
) -> None:
    post_counts: dict[str, int] = {}
    audio = _wav_bytes()

    def transport(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/v3/"):
            assert request.headers.get("x-api-key") == "hg-secret"
        else:
            assert request.headers.get("x-api-key") is None
        if request.method == "GET" and request.url.path == "/v3/voices":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "voice_id": "my-voice",
                            "name": "本人声音",
                            "language": "Chinese",
                            "gender": "male",
                            "support_pause": True,
                            "support_locale": True,
                            "preview_audio_url": "https://api.heygen.test/previews/my-voice.mp3",
                        }
                    ],
                    "has_more": False,
                    "next_token": None,
                },
            )
        if request.method == "POST" and request.url.path == "/v3/voices/speech":
            payload = json.loads(request.content)
            text = str(payload["text"])
            post_counts[text] = post_counts.get(text, 0) + 1
            if text == "第5页旁白" and post_counts[text] == 1:
                return httpx.Response(500, json={"error": {"code": "internal_error"}})
            page = text.removeprefix("第").removesuffix("页旁白")
            return httpx.Response(
                200,
                json={
                    "data": {
                        "audio_url": f"https://api.heygen.test/audio/{page}.wav",
                        "duration": 500,
                        "request_id": f"request-{page}",
                        "word_timestamps": [],
                    }
                },
            )
        if request.method == "GET" and request.url.path.startswith("/audio/"):
            return httpx.Response(200, content=audio, headers={"Content-Type": "audio/wav"})
        raise AssertionError(f"unexpected request {request.method} {request.url}")

    app = create_app(
        tmp_path,
        secret_protector=TestProtector(),
        heygen_transport=httpx.MockTransport(transport),
    )
    with TestClient(app) as api:
        project = api.post("/api/projects", json={"name": "HeyGen八页"}).json()["data"]
        project_id = UUID(project["id"])
        service = app.state.project_service
        manifest = service.get(project_id)
        pages = []
        revisions = []
        for order in range(1, 9):
            revision = uuid4()
            revisions.append(revision)
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
        service.save(manifest.model_copy(update={"pages": pages}))
        profile = api.post(
            "/api/settings/heygen-profiles",
            json={
                "name": "HeyGen本人声音",
                "base_url": "https://api.heygen.test",
                "api_key": "hg-secret",
            },
        ).json()["data"]
        voices = api.get(f"/api/settings/heygen-profiles/{profile['id']}/voices")
        assert voices.json()["data"][0]["name"] == "本人声音"

        for page, revision in zip(pages, revisions, strict=True):
            response = api.post(
                f"/api/projects/{project_id}/audio/heygen/{page.id}",
                json={
                    "profile_id": profile["id"],
                    "revision_id": str(revision),
                    "voice_id": "my-voice",
                    "speed": 1.0,
                },
            )
            assert response.status_code == 201
        assert all(
            count == (2 if text == "第5页旁白" else 1) for text, count in post_counts.items()
        )

        cached = api.post(
            f"/api/projects/{project_id}/audio/heygen/{pages[0].id}",
            json={
                "profile_id": profile["id"],
                "revision_id": str(revisions[0]),
                "voice_id": "my-voice",
                "speed": 1.0,
            },
        )
        assert cached.status_code == 200
        assert post_counts["第1页旁白"] == 1
        changed_voice = api.post(
            f"/api/projects/{project_id}/audio/heygen/{pages[0].id}",
            json={
                "profile_id": profile["id"],
                "revision_id": str(revisions[0]),
                "voice_id": "other-voice",
                "speed": 1.0,
            },
        )
        assert changed_voice.status_code == 409

        replaced = api.post(
            f"/api/projects/{project_id}/audio/heygen/{pages[0].id}",
            json={
                "profile_id": profile["id"],
                "revision_id": str(revisions[0]),
                "voice_id": "other-voice",
                "speed": 1.0,
                "replace_existing": True,
            },
        )
        assert replaced.status_code == 201
        assert post_counts["第1页旁白"] == 2

        restored_voice = api.post(
            f"/api/projects/{project_id}/audio/heygen/{pages[0].id}",
            json={
                "profile_id": profile["id"],
                "revision_id": str(revisions[0]),
                "voice_id": "my-voice",
                "speed": 1.0,
                "replace_existing": True,
            },
        )
        assert restored_voice.status_code == 201
        assert post_counts["第1页旁白"] == 3

    settings = (tmp_path / "settings" / "heygen-profiles.json").read_text(encoding="utf-8")
    assert "hg-secret" not in settings
    saved_manifest = app.state.project_service.get(project_id)
    assert all(page.audio and page.audio.source == "heygen" for page in saved_manifest.pages)

    legacy_page = saved_manifest.pages[1].model_copy(
        update={
            "audio": saved_manifest.pages[1].audio.model_copy(
                update={"narration_revision_id": None}
            )
            if saved_manifest.pages[1].audio
            else None
        }
    )
    app.state.project_service.save(
        saved_manifest.model_copy(
            update={
                "pages": [
                    legacy_page if page.id == legacy_page.id else page
                    for page in saved_manifest.pages
                ]
            }
        )
    )

    with TestClient(app) as api:
        backfilled = api.post(
            f"/api/projects/{project_id}/audio/heygen/{legacy_page.id}",
            json={
                "profile_id": profile["id"],
                "revision_id": str(revisions[1]),
                "voice_id": "my-voice",
                "speed": 1.0,
            },
        )
        assert backfilled.status_code == 200
        assert post_counts["第1页旁白"] == 3

    current = app.state.project_service.get(project_id)
    resolved = AudioService(tmp_path).resolve_page_audio(current)
    assert len(resolved) == 8
    assert all(item.source == "heygen" and item.duration_ms > 0 for item in resolved)
    assert current.pages[1].audio is not None
    assert current.pages[1].audio.narration_revision_id == revisions[1]
    assert any(event.action == "heygen_page_revision_backfilled" for event in current.audit_log)

    with TestClient(app) as api:
        gate = api.get(f"/api/projects/{project_id}/audio/gate")
        assert gate.status_code == 200
        assert gate.json()["data"] == {"allowed": True, "reasons": []}
        assert api.patch(f"/api/projects/{project_id}/step", json={"step": 6}).status_code == 200

    local_page = current.pages[2].model_copy(
        update={
            "audio": current.pages[2].audio.model_copy(update={"source": "local"})
            if current.pages[2].audio
            else None
        }
    )
    app.state.project_service.save(
        current.model_copy(
            update={
                "pages": [
                    local_page if page.id == local_page.id else page for page in current.pages
                ]
            }
        )
    )
    with TestClient(app) as api:
        blocked_switch = api.post(
            f"/api/projects/{project_id}/audio/heygen/{pages[0].id}",
            json={
                "profile_id": profile["id"],
                "revision_id": str(revisions[0]),
                "voice_id": "other-voice",
                "speed": 1.0,
                "replace_existing": True,
            },
        )
    assert blocked_switch.status_code == 409
    assert blocked_switch.json()["error"]["code"] == "audio_route_switch_required"
    assert post_counts["第1页旁白"] == 3

    with TestClient(app) as api:
        gate = api.get(f"/api/projects/{project_id}/audio/gate")
        assert gate.status_code == 200
        assert gate.json()["data"]["allowed"] is False
        assert {reason["code"] for reason in gate.json()["data"]["reasons"]} == {
            "audio_route_mixed"
        }
