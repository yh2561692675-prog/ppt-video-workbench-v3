from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from peripheral_contracts import JobEnvelope
from workbench.audio.ffmpeg import AudioQuality, NormalizedAudio
from workbench.business_modules.p07_audio.policy import (
    PaidRequestCheckpoint,
    PaidRequestRecord,
    synthesis_cache_key,
)


def test_paid_request_checkpoint_reuses_remote_identity_after_attempt_recovery(
    tmp_path: Path,
) -> None:
    page_id = uuid4()
    revision_id = uuid4()
    cache_key = synthesis_cache_key(revision_id, "voice-1", 1.0)
    first = PaidRequestCheckpoint(tmp_path / "0001" / "recovery" / "paid-requests.json")
    record = PaidRequestRecord(
        page_id=page_id,
        cache_key=cache_key,
        request_id="remote-request-1",
        audio_url="https://audio.invalid/remote-request-1.wav",
    )
    first.save({page_id: record})

    second_path = tmp_path / "0002" / "recovery" / "paid-requests.json"
    second_path.parent.mkdir(parents=True)
    second_path.write_bytes(first.path.read_bytes())
    restored = PaidRequestCheckpoint(second_path).load()

    assert restored[page_id].request_id == "remote-request-1"
    assert restored[page_id].cache_key == cache_key


def test_synthesis_recovery_downloads_saved_request_without_resubmitting(
    tmp_path: Path, monkeypatch
) -> None:
    from workbench.business_modules.p07_audio import runner
    from workbench.integrations.heygen.client import DownloadedAudio

    page_id = uuid4()
    revision_id = uuid4()
    profile_id = uuid4()
    cache_key = synthesis_cache_key(revision_id, "voice-1", 1.0)
    checkpoint = PaidRequestCheckpoint(tmp_path / "recovery" / "paid-requests.json")
    checkpoint.save(
        {
            page_id: PaidRequestRecord(
                page_id=page_id,
                cache_key=cache_key,
                request_id="remote-request-1",
                audio_url="https://audio.invalid/remote-request-1.wav",
            )
        }
    )

    class FakeClient:
        generate_calls = 0

        def generate_speech(self, *args, **kwargs):
            self.generate_calls += 1
            raise AssertionError("recovery must not resubmit a paid request")

        def download(self, url: str) -> DownloadedAudio:
            assert url.endswith("remote-request-1.wav")
            return DownloadedAudio(content=b"remote wav", content_type="audio/wav")

    fake = FakeClient()

    def fake_normalize(source: Path, output_dir: Path) -> NormalizedAudio:
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / "recovered.wav"
        target.write_bytes(b"normalized wav")
        return NormalizedAudio(
            original_path=source,
            wav_path=target,
            duration_ms=1000,
            sample_rate=16000,
            channels=1,
            sha256="a" * 64,
            quality=AudioQuality(-1, 0, [], False),
            command_summary="fake",
        )

    monkeypatch.setattr(runner, "HeyGenClient", lambda: fake)
    monkeypatch.setattr(runner, "normalize_audio", fake_normalize)
    monkeypatch.setenv("WORKBENCH_HEYGEN_PROFILE_ID", str(profile_id))
    monkeypatch.setenv("WORKBENCH_HEYGEN_BASE_URL", "https://api.heygen.invalid")
    monkeypatch.setenv("WORKBENCH_HEYGEN_API_KEY", "secret-never-persisted")
    job = JobEnvelope(
        schema_version="1.0",
        job_id=uuid4(),
        project_id=uuid4(),
        job_type="audio.synthesize",
        requested_by="test",
        idempotency_key=uuid4().hex,
        parameters={
            "project_revision": 1,
            "profile_id": str(profile_id),
            "voice_id": "voice-1",
            "speed": 1,
            "existing_route": "none",
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

    execution = runner._handle(job, tmp_path)

    assert fake.generate_calls == 0
    assert execution.business_result.payload["remote_requests"][0]["reused"] is True
    assert "secret-never-persisted" not in execution.business_result.model_dump_json()
