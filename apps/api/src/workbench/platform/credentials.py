"""Platform credential-store boundary with deterministic test backend.

OS-specific implementations (Windows Credential Manager, macOS Keychain and
Linux Secret Service) plug into `CredentialBackend`; domain objects only see
credential references and metadata.
"""

from __future__ import annotations

import importlib
import re
from datetime import UTC, datetime
from typing import Any, Protocol

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


_CREDENTIAL_REF = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")
_NATIVE_BACKEND_MARKERS = {
    "windows": ("keyring.backends.windows", "keyring.backends.winvault"),
    "macos": ("keyring.backends.macos",),
    "linux": ("keyring.backends.secretservice",),
}


def _validate_credential_ref(credential_ref: str) -> None:
    if _CREDENTIAL_REF.fullmatch(credential_ref) is None:
        raise CredentialStoreError("invalid credential_ref")


class KeyringCredentialBackend(UnavailableCredentialBackend):
    """Adapter for an OS keyring selected by the optional ``keyring`` package.

    The adapter accepts only platform-native keyring implementations.  It
    deliberately rejects fail/null/file backends so an absent desktop keyring
    never degrades into plaintext persistence.
    """

    def __init__(self, keyring_api: Any | None, *, name: str, service_name: str) -> None:
        self.name = name
        self._keyring = keyring_api
        self._service_name = service_name
        self.available = keyring_api is not None

    def set_secret(self, credential_ref: str, secret: str) -> None:
        if not secret:
            raise CredentialStoreError("secret must not be empty")
        keyring = self._require_keyring()
        self._operate(
            credential_ref,
            lambda: keyring.set_password(self._service_name, credential_ref, secret),
        )

    def get_secret(self, credential_ref: str) -> str:
        keyring = self._require_keyring()
        value = self._operate(
            credential_ref,
            lambda: keyring.get_password(self._service_name, credential_ref),
        )
        if not isinstance(value, str) or not value:
            raise CredentialStoreError("credential not found")
        return value

    def delete_secret(self, credential_ref: str) -> None:
        keyring = self._require_keyring()
        self._operate(
            credential_ref,
            lambda: keyring.delete_password(self._service_name, credential_ref),
        )

    def _require_keyring(self) -> Any:
        if not self.available or self._keyring is None:
            raise CredentialStoreError("system credential service unavailable")
        return self._keyring

    def _operate(self, credential_ref: str, operation: Any) -> Any:
        _validate_credential_ref(credential_ref)
        if not self.available or self._keyring is None:
            raise CredentialStoreError("system credential service unavailable")
        try:
            return operation()
        except CredentialStoreError:
            raise
        except Exception as error:
            raise CredentialStoreError("system credential operation failed") from error


class WindowsCredentialBackend(KeyringCredentialBackend):
    name = "windows-credential-manager"

    def __init__(self, keyring_api: Any | None = None) -> None:
        super().__init__(
            keyring_api,
            name=self.name,
            service_name="ppt-video-workbench",
        )


class MacOSKeychainBackend(KeyringCredentialBackend):
    name = "macos-keychain"

    def __init__(self, keyring_api: Any | None = None) -> None:
        super().__init__(
            keyring_api,
            name=self.name,
            service_name="ppt-video-workbench",
        )


class LinuxSecretServiceBackend(KeyringCredentialBackend):
    name = "linux-secret-service"

    def __init__(self, keyring_api: Any | None = None) -> None:
        super().__init__(
            keyring_api,
            name=self.name,
            service_name="ppt-video-workbench",
        )


def _native_keyring(platform_name: str) -> Any | None:
    try:
        keyring = importlib.import_module("keyring")
        backend = keyring.get_keyring()
    except Exception:
        return None
    identity = f"{type(backend).__module__}.{type(backend).__name__}".lower()
    if not any(marker in identity for marker in _NATIVE_BACKEND_MARKERS[platform_name]):
        return None
    return keyring


def system_credential_backend(platform_name: str) -> CredentialBackend:
    """Select a native OS boundary, failing closed when its optional binding is absent."""

    if platform_name == "windows":
        return WindowsCredentialBackend(_native_keyring(platform_name))
    if platform_name == "macos":
        return MacOSKeychainBackend(_native_keyring(platform_name))
    if platform_name == "linux":
        return LinuxSecretServiceBackend(_native_keyring(platform_name))
    raise ValueError("unsupported platform credential backend")


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
