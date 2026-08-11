"""Credential references and an in-memory fake secret store.

The secret value is deliberately only reachable through the adapter-facing
`get_secret` method. API/domain objects expose metadata, never the value.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from pydantic import Field

from workbench.contracts.p2_platform import _ContractModel


class CredentialStoreError(RuntimeError):
    pass


class CredentialMetadataV1(_ContractModel):
    schema_version: int = 1
    credential_ref: str = Field(pattern=r"^[a-z][a-z0-9_.:-]{0,127}$")
    provider_id: str = Field(pattern=r"^[a-z][a-z0-9_.-]{0,63}$")
    scope: str = Field(min_length=1, max_length=200)
    status: str = Field(pattern=r"^(active|revoked|degraded)$")
    created_at: datetime
    updated_at: datetime
    last_validated_at: datetime | None = None


class CredentialStore(Protocol):
    def put(
        self, credential_ref: str, provider_id: str, secret: str, scope: str
    ) -> CredentialMetadataV1: ...

    def get_secret(self, credential_ref: str) -> str: ...

    def metadata(self, credential_ref: str) -> CredentialMetadataV1: ...

    def list_metadata(self) -> list[CredentialMetadataV1]: ...

    def rotate(self, credential_ref: str, secret: str) -> CredentialMetadataV1: ...

    def revoke(self, credential_ref: str) -> CredentialMetadataV1: ...


class InMemoryCredentialStore:
    """Deterministic fake for unit tests; never serializes secrets."""

    def __init__(self) -> None:
        self._secrets: dict[str, str] = {}
        self._metadata: dict[str, CredentialMetadataV1] = {}

    def put(
        self, credential_ref: str, provider_id: str, secret: str, scope: str
    ) -> CredentialMetadataV1:
        if not secret:
            raise CredentialStoreError("secret must not be empty")
        if credential_ref in self._metadata:
            raise CredentialStoreError("credential_ref already exists")
        now = datetime.now(UTC)
        metadata = CredentialMetadataV1(
            credential_ref=credential_ref,
            provider_id=provider_id,
            scope=scope,
            status="active",
            created_at=now,
            updated_at=now,
        )
        self._secrets[credential_ref] = secret
        self._metadata[credential_ref] = metadata
        return metadata

    def get_secret(self, credential_ref: str) -> str:
        metadata = self.metadata(credential_ref)
        if metadata.status != "active":
            raise CredentialStoreError("credential is not active")
        try:
            return self._secrets[credential_ref]
        except KeyError as error:
            raise CredentialStoreError("credential not found") from error

    def metadata(self, credential_ref: str) -> CredentialMetadataV1:
        try:
            return self._metadata[credential_ref]
        except KeyError as error:
            raise CredentialStoreError("credential not found") from error

    def list_metadata(self) -> list[CredentialMetadataV1]:
        return sorted(self._metadata.values(), key=lambda item: item.credential_ref)

    def rotate(self, credential_ref: str, secret: str) -> CredentialMetadataV1:
        if not secret:
            raise CredentialStoreError("secret must not be empty")
        metadata = self.metadata(credential_ref)
        now = datetime.now(UTC)
        self._secrets[credential_ref] = secret
        updated = metadata.model_copy(update={"status": "active", "updated_at": now})
        self._metadata[credential_ref] = updated
        return updated

    def revoke(self, credential_ref: str) -> CredentialMetadataV1:
        metadata = self.metadata(credential_ref)
        updated = metadata.model_copy(update={"status": "revoked", "updated_at": datetime.now(UTC)})
        self._metadata[credential_ref] = updated
        return updated


def redact_sensitive(value: str) -> str:
    """Redact common credential-bearing fields before diagnostics/logging."""

    lower = value.lower()
    markers = ("api_key", "apikey", "authorization", "bearer ", "cookie", "token", "secret")
    if any(marker in lower for marker in markers):
        return "[REDACTED]"
    return value
