"""Tenant-scoped deterministic provider result cache."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from workbench.contracts.p2_platform import canonical_sha256

from .models import ProviderInvocationResultV1


def cache_identity(
    *,
    provider_id: str,
    capability_id: str,
    adapter_version: str,
    model_resolved: str | None,
    parameters: dict[str, Any],
    input_fingerprints: list[str],
    output_schema_version: str,
    locale: str | None = None,
    region: str | None = None,
    deterministic_seed: int | None = None,
    tenant_scope: str | None = None,
    platform_fingerprint: str | None = None,
    runtime_fingerprint: str | None = None,
    font_fingerprint: str | None = None,
    cloud_revision_id: str | None = None,
) -> str:
    """Build a cache key that cannot cross providers, versions, or tenants."""

    return canonical_sha256(
        {
            "provider_id": provider_id,
            "capability_id": capability_id,
            "adapter_version": adapter_version,
            "model_resolved": model_resolved,
            "parameters": parameters,
            "input_fingerprints": input_fingerprints,
            "output_schema_version": output_schema_version,
            "locale": locale,
            "region": region,
            "deterministic_seed": deterministic_seed,
            "tenant_scope": tenant_scope,
            "platform_fingerprint": platform_fingerprint,
            "runtime_fingerprint": runtime_fingerprint,
            "font_fingerprint": font_fingerprint,
            "cloud_revision_id": cloud_revision_id,
        }
    )


@dataclass(frozen=True)
class _CacheEntry:
    value: ProviderInvocationResultV1
    expires_at: datetime


class ProviderCache:
    def __init__(self, *, default_ttl_seconds: int = 3600, max_entries: int = 10_000) -> None:
        if default_ttl_seconds < 1 or max_entries < 1:
            raise ValueError("cache limits must be positive")
        self.default_ttl = timedelta(seconds=default_ttl_seconds)
        self.max_entries = max_entries
        self._entries: dict[tuple[str, str], _CacheEntry] = {}

    def get(self, tenant_scope: str, identity: str) -> ProviderInvocationResultV1 | None:
        key = (tenant_scope, identity)
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= datetime.now(UTC):
            self._entries.pop(key, None)
            return None
        return entry.value

    def put(
        self,
        tenant_scope: str,
        identity: str,
        value: ProviderInvocationResultV1,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        if len(self._entries) >= self.max_entries and (tenant_scope, identity) not in self._entries:
            self._evict_expired()
        if len(self._entries) >= self.max_entries:
            self._entries.pop(next(iter(self._entries)))
        ttl = self.default_ttl if ttl_seconds is None else timedelta(seconds=max(1, ttl_seconds))
        self._entries[(tenant_scope, identity)] = _CacheEntry(
            value=value, expires_at=datetime.now(UTC) + ttl
        )

    def invalidate_tenant(self, tenant_scope: str) -> None:
        for key in tuple(self._entries):
            if key[0] == tenant_scope:
                self._entries.pop(key, None)

    def clear(self) -> None:
        self._entries.clear()

    def _evict_expired(self) -> None:
        now = datetime.now(UTC)
        for key, entry in tuple(self._entries.items()):
            if entry.expires_at <= now:
                self._entries.pop(key, None)
