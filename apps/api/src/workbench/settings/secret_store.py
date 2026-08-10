from __future__ import annotations

import base64
import ctypes
import json
import os
import sys
from abc import ABC, abstractmethod
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class SecretProtector(ABC):
    @abstractmethod
    def protect(self, plaintext: bytes) -> bytes: ...

    @abstractmethod
    def unprotect(self, ciphertext: bytes) -> bytes: ...


class SecretStoreUnavailable(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class WindowsDpapiProtector(SecretProtector):
    """Protect secrets for the current Windows user with CryptProtectData."""

    def protect(self, plaintext: bytes) -> bytes:
        return self._crypt(plaintext, decrypt=False)

    def unprotect(self, ciphertext: bytes) -> bytes:
        return self._crypt(ciphertext, decrypt=True)

    def _crypt(self, value: bytes, *, decrypt: bool) -> bytes:
        if sys.platform != "win32":
            raise SecretStoreUnavailable("Windows DPAPI is only available on Windows")
        source_buffer = ctypes.create_string_buffer(value)
        source = _DataBlob(len(value), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
        output = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        kernel32 = ctypes.windll.kernel32
        if decrypt:
            ok = crypt32.CryptUnprotectData(
                ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output)
            )
        else:
            ok = crypt32.CryptProtectData(
                ctypes.byref(source),
                "PPT Video Workbench",
                None,
                None,
                None,
                0,
                ctypes.byref(output),
            )
        if not ok:
            raise SecretStoreUnavailable("Windows DPAPI operation failed")
        try:
            return ctypes.string_at(output.pbData, output.cbData)
        finally:
            kernel32.LocalFree(output.pbData)


class LlmProfilePublic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    base_url: HttpUrl
    base_url_digest: str
    model: str
    has_api_key: bool = True
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None = None


class LlmCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: LlmProfilePublic
    api_key: str = Field(repr=False)


class LlmProfileStore:
    def __init__(self, path: Path, protector: SecretProtector) -> None:
        self._path = path
        self._protector = protector
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, *, name: str, base_url: str, api_key: str, model: str) -> LlmProfilePublic:
        normalized_url = str(HttpUrl(base_url)).rstrip("/")
        if not api_key.strip():
            raise ValueError("API Key is required")
        now = datetime.now(UTC)
        profile_id = uuid4()
        record: dict[str, object] = {
            "id": str(profile_id),
            "name": name.strip(),
            "base_url": normalized_url,
            "base_url_digest": _digest_url(normalized_url),
            "model": model.strip(),
            "encrypted_api_key": base64.b64encode(
                self._protector.protect(api_key.encode("utf-8"))
            ).decode("ascii"),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "last_used_at": None,
        }
        records = self._read()
        records.append(record)
        self._write(records)
        return self._public(record)

    def list_profiles(self) -> list[LlmProfilePublic]:
        return [self._public(record) for record in self._read()]

    def credentials(self, profile_id: UUID) -> LlmCredentials:
        records = self._read()
        for record in records:
            if record["id"] == str(profile_id):
                key = self._protector.unprotect(
                    base64.b64decode(str(record["encrypted_api_key"]))
                ).decode("utf-8")
                return LlmCredentials(profile=self._public(record), api_key=key)
        raise KeyError(profile_id)

    def mark_used(self, profile_id: UUID) -> LlmProfilePublic:
        records = self._read()
        for record in records:
            if record["id"] == str(profile_id):
                record["last_used_at"] = datetime.now(UTC).isoformat()
                record["updated_at"] = record["last_used_at"]
                self._write(records)
                return self._public(record)
        raise KeyError(profile_id)

    def _read(self) -> list[dict[str, object]]:
        if not self._path.exists():
            return []
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("invalid LLM profile store")
        return payload

    def _write(self, records: list[dict[str, object]]) -> None:
        temporary = self._path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(records, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self._path)

    @staticmethod
    def _public(record: dict[str, object]) -> LlmProfilePublic:
        return LlmProfilePublic.model_validate(
            {key: value for key, value in record.items() if key != "encrypted_api_key"}
            | {"has_api_key": True}
        )


def _digest_url(base_url: str) -> str:
    import hashlib

    return hashlib.sha256(base_url.encode("utf-8")).hexdigest()[:16]
