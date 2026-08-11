"""Platform credential-store boundary with deterministic test backend.

OS-specific implementations (Windows Credential Manager, macOS Keychain and
Linux Secret Service) plug into `CredentialBackend`; domain objects only see
credential references and metadata.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from workbench.providers.credentials import (
    CredentialMetadataV1,
    CredentialStoreError,
)


class CredentialBackend(Protocol):
    name: str
    available: bool

    def set_secret(self, credential_ref: str, secret: str) -> None: ...

    def get_secret(self, credential_ref: str) -> str: ...

    def delete_secret(self, credential_ref: str) -> None: ...


class InMemoryCredentialBackend:
    name = "deterministic-fake"
    available = True

    def __init__(self) -> None:
        self._secrets: dict[str, str] = {}

    def set_secret(self, credential_ref: str, secret: str) -> None:
        self._secrets[credential_ref] = secret

    def get_secret(self, credential_ref: str) -> str:
        try:
            return self._secrets[credential_ref]
        except KeyError as error:
            raise CredentialStoreError("credential not found") from error

    def delete_secret(self, credential_ref: str) -> None:
        self._secrets.pop(credential_ref, None)


class UnavailableCredentialBackend:
    """Explicit fallback; it never silently persists secrets to a file."""

    name = "unavailable"
    available = False

    def set_secret(self, credential_ref: str, secret: str) -> None:
        raise CredentialStoreError("system credential service unavailable")

    def get_secret(self, credential_ref: str) -> str:
        raise CredentialStoreError("system credential service unavailable")

    def delete_secret(self, credential_ref: str) -> None:
        raise CredentialStoreError("system credential service unavailable")


class PlatformCredentialStore:
    def __init__(self, backend: CredentialBackend) -> None:
        self.backend = backend
        self._metadata: dict[str, CredentialMetadataV1] = {}

    def put(
        self, credential_ref: str, provider_id: str, secret: str, scope: str
    ) -> CredentialMetadataV1:
        if not secret:
            raise CredentialStoreError("secret must not be empty")
        if credential_ref in self._metadata:
            raise CredentialStoreError("credential_ref already exists")
        self.backend.set_secret(credential_ref, secret)
        now = datetime.now(UTC)
        metadata = CredentialMetadataV1(
            credential_ref=credential_ref,
            provider_id=provider_id,
            scope=scope,
            status="active" if self.backend.available else "degraded",
            created_at=now,
            updated_at=now,
        )
        self._metadata[credential_ref] = metadata
        return metadata

    def get_secret(self, credential_ref: str) -> str:
        metadata = self.metadata(credential_ref)
        if metadata.status != "active":
            raise CredentialStoreError("credential is not active")
        return self.backend.get_secret(credential_ref)

    def metadata(self, credential_ref: str) -> CredentialMetadataV1:
        try:
            return self._metadata[credential_ref]
        except KeyError as error:
            raise CredentialStoreError("credential not found") from error

    def list_metadata(self) -> list[CredentialMetadataV1]:
        """List only non-secret metadata in a stable order."""

        return sorted(self._metadata.values(), key=lambda item: item.credential_ref)

    def rotate(self, credential_ref: str, secret: str) -> CredentialMetadataV1:
        if not secret:
            raise CredentialStoreError("secret must not be empty")
        metadata = self.metadata(credential_ref)
        self.backend.set_secret(credential_ref, secret)
        updated = metadata.model_copy(update={"status": "active", "updated_at": datetime.now(UTC)})
        self._metadata[credential_ref] = updated
        return updated

    def revoke(self, credential_ref: str) -> CredentialMetadataV1:
        metadata = self.metadata(credential_ref)
        self.backend.delete_secret(credential_ref)
        updated = metadata.model_copy(update={"status": "revoked", "updated_at": datetime.now(UTC)})
        self._metadata[credential_ref] = updated
        return updated
