"""Static/health/sample capability probing with TTL and in-flight de-duplication."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Literal

from workbench.contracts.p2_platform import OperationContextV1

from .adapter import ProviderAdapter
from .models import ProviderHealthV1, ProviderInvocationV1

ProbeMode = Literal["static", "health", "sample"]


@dataclass(frozen=True)
class ProbeSnapshotV1:
    provider_id: str
    capability_id: str
    mode: ProbeMode
    health: ProviderHealthV1
    observed_at: datetime
    expires_at: datetime
    billed_probe: bool
    evidence_sha256: str


class ProbeConfirmationRequired(PermissionError):
    pass


class CapabilityProbeService:
    def __init__(self, *, default_ttl_seconds: int = 300) -> None:
        self.default_ttl = timedelta(seconds=max(1, default_ttl_seconds))
        self._cache: dict[tuple[str, str, ProbeMode], ProbeSnapshotV1] = {}
        self._inflight: dict[tuple[str, str, ProbeMode], asyncio.Task[ProbeSnapshotV1]] = {}
        self._lock = asyncio.Lock()

    async def probe(
        self,
        adapter: ProviderAdapter,
        context: OperationContextV1,
        *,
        capability_id: str,
        mode: ProbeMode = "health",
        confirm_billed_sample: bool = False,
        force: bool = False,
    ) -> ProbeSnapshotV1:
        if mode == "sample" and not confirm_billed_sample:
            raise ProbeConfirmationRequired("sample probing requires explicit billing confirmation")
        key = (adapter.descriptor.provider_id, capability_id, mode)
        now = datetime.now(UTC)
        if not force:
            cached = self._cache.get(key)
            if cached is not None and cached.expires_at > now:
                return cached
        async with self._lock:
            if not force and key in self._inflight:
                return await self._inflight[key]
            task = asyncio.create_task(self._run_probe(adapter, context, capability_id, mode))
            self._inflight[key] = task
        try:
            return await task
        finally:
            async with self._lock:
                if self._inflight.get(key) is task:
                    self._inflight.pop(key, None)

    async def _run_probe(
        self,
        adapter: ProviderAdapter,
        context: OperationContextV1,
        capability_id: str,
        mode: ProbeMode,
    ) -> ProbeSnapshotV1:
        invocation = ProviderInvocationV1(
            operation=context,
            provider_id=adapter.descriptor.provider_id,
            capability_id=capability_id,
            input_refs=[],
            parameters={"probe.mode": mode},
            expected_output_schema="provider-health-v1",
        )
        health = await asyncio.wait_for(
            adapter.probe(invocation), timeout=context.budget.timeout_ms / 1000
        )
        observed = datetime.now(UTC)
        expires = observed + self.default_ttl
        evidence = sha256(
            f"{health.provider_id}|{health.status}|{health.observed_at}|{mode}".encode()
        ).hexdigest()
        snapshot = ProbeSnapshotV1(
            provider_id=health.provider_id,
            capability_id=capability_id,
            mode=mode,
            health=health,
            observed_at=observed,
            expires_at=expires,
            billed_probe=mode == "sample",
            evidence_sha256=f"sha256:{evidence}",
        )
        self._cache[(health.provider_id, capability_id, mode)] = snapshot
        return snapshot

    def invalidate(self, provider_id: str | None = None) -> None:
        if provider_id is None:
            self._cache.clear()
        else:
            for key in tuple(self._cache):
                if key[0] == provider_id:
                    self._cache.pop(key, None)
