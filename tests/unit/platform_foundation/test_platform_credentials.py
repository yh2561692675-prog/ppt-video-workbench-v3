from __future__ import annotations

import pytest
from workbench.platform.credentials import (
    InMemoryCredentialBackend,
    PlatformCredentialStore,
    UnavailableCredentialBackend,
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
