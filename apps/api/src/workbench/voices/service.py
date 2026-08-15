"""Authorization-aware local voice identity service."""

from __future__ import annotations

from .models import VoiceAuthorizationV1, VoiceIdentityV1
from .repository import VoiceRepository


class VoiceAuthorizationService:
    def __init__(self, repository: VoiceRepository) -> None:
        self.repository = repository

    def grant(self, authorization: VoiceAuthorizationV1) -> VoiceAuthorizationV1:
        return self.repository.add_authorization(authorization)

    def register_voice(self, voice: VoiceIdentityV1) -> VoiceIdentityV1:
        return self.repository.add_voice(voice)

    def revoke(self, voice_id: str) -> VoiceIdentityV1:
        return self.repository.revoke_voice(voice_id)

    def can_use(self, voice_id: str, scope: str) -> bool:
        voice = self.repository.get_voice(voice_id)
        if voice.status != "active":
            return False
        authorization = self.repository.authorization(voice.authorization_id)
        return authorization.status == "active" and scope in authorization.scopes
