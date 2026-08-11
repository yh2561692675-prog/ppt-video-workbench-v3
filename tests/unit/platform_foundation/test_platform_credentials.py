from __future__ import annotations

import pytest
from workbench.platform.credentials import (
    InMemoryCredentialBackend,
    LinuxSecretServiceBackend,
    MacOSKeychainBackend,
    PlatformCredentialStore,
    UnavailableCredentialBackend,
    WindowsCredentialBackend,
    system_credential_backend,
)
from workbench.providers.credentials import CredentialStoreError, redact_sensitive


class FakeNativeKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self.values[(service, username)] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self.values.get((service, username))

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


def test_platform_credential_store_exposes_metadata_not_secret() -> None:
    store = PlatformCredentialStore(InMemoryCredentialBackend())
    metadata = store.put("llm.main", "builtin-llm", "secret-value", "tenant:test")
    assert metadata.status == "active"
    assert "secret-value" not in str(metadata.model_dump())
    assert [item.credential_ref for item in store.list_metadata()] == ["llm.main"]
    assert store.get_secret("llm.main") == "secret-value"
    store.revoke("llm.main")
    with pytest.raises(CredentialStoreError):
        store.get_secret("llm.main")
    assert redact_sensitive("Authorization: Bearer secret-value") == "[REDACTED]"


def test_optional_native_backend_round_trip_keeps_secret_out_of_metadata() -> None:
    backend = WindowsCredentialBackend(FakeNativeKeyring())
    assert backend.available is True
    store = PlatformCredentialStore(backend)
    metadata = store.put("llm.native", "builtin-llm", "secret-value", "tenant:test")
    assert metadata.status == "active"
    assert store.get_secret("llm.native") == "secret-value"
    assert "secret-value" not in str(store.list_metadata())
    store.revoke("llm.native")
    with pytest.raises(CredentialStoreError):
        store.get_secret("llm.native")


def test_optional_native_backend_rejects_unsafe_reference() -> None:
    backend = WindowsCredentialBackend(FakeNativeKeyring())
    with pytest.raises(CredentialStoreError, match="invalid credential_ref"):
        backend.set_secret("../escape", "secret-value")


def test_unavailable_system_store_fails_closed() -> None:
    store = PlatformCredentialStore(UnavailableCredentialBackend())
    with pytest.raises(CredentialStoreError):
        store.put("llm.main", "builtin-llm", "secret-value", "tenant:test")


@pytest.mark.parametrize(
    ("platform_name", "backend_type"),
    [
        ("windows", WindowsCredentialBackend),
        ("macos", MacOSKeychainBackend),
        ("linux", LinuxSecretServiceBackend),
    ],
)
def test_system_credential_backend_is_explicitly_fail_closed(
    platform_name: str, backend_type: type
) -> None:
    backend = system_credential_backend(platform_name)
    assert isinstance(backend, backend_type)
    assert backend.available is False
