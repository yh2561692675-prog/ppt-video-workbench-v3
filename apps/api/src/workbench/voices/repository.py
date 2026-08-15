"""Atomic workspace persistence for voice authorization and identities."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path
from threading import RLock
from uuid import UUID

from .models import VoiceAuthorizationV1, VoiceIdentityV1


class VoiceRepositoryError(RuntimeError):
    pass


class VoiceRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "voices.json"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._authorizations: dict[str, VoiceAuthorizationV1] = {}
        self._voices: dict[str, VoiceIdentityV1] = {}
        self._load()

    def add_authorization(self, authorization: VoiceAuthorizationV1) -> VoiceAuthorizationV1:
        with self._lock:
            key = str(authorization.authorization_id)
            if key in self._authorizations:
                raise VoiceRepositoryError("authorization_exists")
            self._authorizations[key] = authorization
            self._save()
            return authorization

    def add_voice(self, voice: VoiceIdentityV1) -> VoiceIdentityV1:
        with self._lock:
            if voice.voice_id in self._voices:
                raise VoiceRepositoryError("voice_exists")
            authorization = self._authorizations.get(str(voice.authorization_id))
            if authorization is None:
                raise VoiceRepositoryError("authorization_not_found")
            required_scope = "local_clone" if voice.kind == "local_clone" else "local_tts"
            if authorization.status != "active" or required_scope not in authorization.scopes:
                raise VoiceRepositoryError("voice_authorization_not_active")
            self._voices[voice.voice_id] = voice
            self._save()
            return voice

    def list_voices(self, *, active_only: bool = False) -> list[VoiceIdentityV1]:
        with self._lock:
            values: Iterable[VoiceIdentityV1] = self._voices.values()
            if active_only:
                values = (item for item in values if item.status == "active")
            return sorted(values, key=lambda item: item.voice_id)

    def get_voice(self, voice_id: str) -> VoiceIdentityV1:
        try:
            return self._voices[voice_id]
        except KeyError as error:
            raise VoiceRepositoryError("voice_not_found") from error

    def revoke_voice(self, voice_id: str) -> VoiceIdentityV1:
        with self._lock:
            voice = self.get_voice(voice_id)
            updated = voice.model_copy(update={"status": "revoked"})
            self._voices[voice_id] = updated
            self._save()
            return updated

    def authorization(self, authorization_id: UUID) -> VoiceAuthorizationV1:
        try:
            return self._authorizations[str(authorization_id)]
        except KeyError as error:
            raise VoiceRepositoryError("authorization_not_found") from error

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self._authorizations = {
                item["authorization_id"]: VoiceAuthorizationV1.model_validate(item)
                for item in payload.get("authorizations", [])
            }
            self._voices = {
                item["voice_id"]: VoiceIdentityV1.model_validate(item)
                for item in payload.get("voices", [])
            }
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise VoiceRepositoryError("voice_repository_corrupt") from error

    def _save(self) -> None:
        payload = {
            "schema_version": 1,
            "authorizations": [
                item.model_dump(mode="json") for item in self._authorizations.values()
            ],
            "voices": [item.model_dump(mode="json") for item in self._voices.values()],
        }
        fd, raw_path = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.root)
        temp_path = Path(raw_path)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
