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
