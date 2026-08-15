from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from workbench.voices.models import VoiceAuthorizationV1, VoiceIdentityV1
from workbench.voices.repository import VoiceRepository, VoiceRepositoryError
from workbench.voices.service import VoiceAuthorizationService


def _authorization() -> VoiceAuthorizationV1:
    return VoiceAuthorizationV1(
        subject="self",
        granted_by="owner",
        scopes=["local_clone", "local_tts"],
        source_audio_sha256="a" * 64,
    )


def test_voice_requires_active_local_authorization_and_survives_restart(tmp_path: Path) -> None:
    repository = VoiceRepository(tmp_path / "voices")
    service = VoiceAuthorizationService(repository)
    authorization = service.grant(_authorization())
    voice = service.register_voice(
        VoiceIdentityV1(
            voice_id="owner-voice",
            display_name="Owner voice",
            kind="local_clone",
            model_id="local-clone",
            model_revision="r1",
            authorization_id=authorization.authorization_id,
            sample_refs=["asset:voice-sample"],
        )
    )
    assert service.can_use(voice.voice_id, "local_clone") is True

    restarted = VoiceRepository(tmp_path / "voices")
    assert restarted.get_voice("owner-voice").local_only is True
    VoiceAuthorizationService(restarted).revoke("owner-voice")
    assert VoiceAuthorizationService(restarted).can_use("owner-voice", "local_clone") is False


def test_voice_registration_rejects_missing_authorization(tmp_path: Path) -> None:
    repository = VoiceRepository(tmp_path / "voices")
    with pytest.raises(VoiceRepositoryError, match="authorization_not_found"):
        repository.add_voice(
            VoiceIdentityV1(
                voice_id="unowned-voice",
                display_name="Unowned",
                kind="local_clone",
                model_id="local-clone",
                model_revision="r1",
                authorization_id=uuid4(),
            )
        )
