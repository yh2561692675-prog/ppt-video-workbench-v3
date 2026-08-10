from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from workbench.settings.secret_store import SecretProtector


class HeyGenProfilePublic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    base_url: HttpUrl
    base_url_digest: str
    has_api_key: bool = True
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None


class HeyGenCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: HeyGenProfilePublic
    api_key: str = Field(repr=False)


class HeyGenProfileStore:
    def __init__(self, path: Path, protector: SecretProtector) -> None:
        self.path = path
        self.protector = protector
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, *, name: str, base_url: str, api_key: str) -> HeyGenProfilePublic:
        normalized = str(HttpUrl(base_url)).rstrip("/")
        if not api_key.strip():
            raise ValueError("API Key is required")
        now = datetime.now(UTC)
        record: dict[str, object] = {
            "id": str(uuid4()),
            "name": name.strip(),
            "base_url": normalized,
            "base_url_digest": hashlib.sha256(normalized.encode()).hexdigest()[:16],
            "encrypted_api_key": base64.b64encode(
                self.protector.protect(api_key.encode())
            ).decode(),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "last_used_at": None,
        }
        records = self._read()
        records.append(record)
        self._write(records)
        return self._public(record)

    def credentials(self, profile_id: UUID) -> HeyGenCredentials:
        for record in self._read():
            if record["id"] == str(profile_id):
                api_key = self.protector.unprotect(
                    base64.b64decode(str(record["encrypted_api_key"]))
                ).decode()
                return HeyGenCredentials(profile=self._public(record), api_key=api_key)
        raise KeyError(profile_id)

    def update(
        self, profile_id: UUID, *, name: str, base_url: str, api_key: str
    ) -> HeyGenProfilePublic:
        normalized = str(HttpUrl(base_url)).rstrip("/")
        if not name.strip():
            raise ValueError("HeyGen profile name is required")
        if not api_key.strip():
            raise ValueError("API Key is required")
        records = self._read()
        for record in records:
            if record["id"] == str(profile_id):
                now = datetime.now(UTC).isoformat()
                record.update(
                    {
                        "name": name.strip(),
                        "base_url": normalized,
                        "base_url_digest": hashlib.sha256(normalized.encode()).hexdigest()[:16],
                        "encrypted_api_key": base64.b64encode(
                            self.protector.protect(api_key.encode())
                        ).decode(),
                        "updated_at": now,
                    }
                )
                self._write(records)
                return self._public(record)
        raise KeyError(profile_id)

    def list_profiles(self) -> list[HeyGenProfilePublic]:
        return [self._public(item) for item in self._read()]

    def mark_used(self, profile_id: UUID) -> None:
        records = self._read()
        for record in records:
            if record["id"] == str(profile_id):
                now = datetime.now(UTC).isoformat()
                record["last_used_at"] = now
                record["updated_at"] = now
                self._write(records)
                return
        raise KeyError(profile_id)

    def _read(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("invalid HeyGen profile store")
        return payload

    def _write(self, records: list[dict[str, object]]) -> None:
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(records, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    @staticmethod
    def _public(record: dict[str, object]) -> HeyGenProfilePublic:
        return HeyGenProfilePublic.model_validate(
            {key: value for key, value in record.items() if key != "encrypted_api_key"}
            | {"has_api_key": True}
        )
