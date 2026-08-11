from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from workbench.providers.adapter import DeterministicFakeProvider
from workbench.providers.api import ProviderApiState, create_provider_router
from workbench.providers.artifacts import ArtifactPublisher, ArtifactValidationError
from workbench.providers.billing import BudgetLedger, PriceBookV1, PriceLineV1, ProviderRateLimiter
from workbench.providers.credentials import InMemoryCredentialStore, redact_sensitive
from workbench.providers.policy import ProviderPolicyEvaluator, ProviderPolicyV1, failover_allowed
from workbench.providers.probe import CapabilityProbeService, ProbeConfirmationRequired
from workbench.providers.registry import ProviderRegistry

from .test_provider_platform import context, descriptor


@pytest.mark.asyncio
async def test_probe_requires_sample_confirmation_and_reuses_ttl_cache() -> None:
    fake = DeterministicFakeProvider(descriptor("fake-a"))
    service = CapabilityProbeService(default_ttl_seconds=60)
    ctx = context()
    with pytest.raises(ProbeConfirmationRequired):
        await service.probe(fake, ctx, capability_id="synthesize.speech", mode="sample")
    first = await service.probe(fake, ctx, capability_id="synthesize.speech")
    second = await service.probe(fake, ctx, capability_id="synthesize.speech")
    assert first is second
    assert first.billed_probe is False


@pytest.mark.asyncio
async def test_probe_concurrent_requests_are_deduplicated() -> None:
    fake = DeterministicFakeProvider(descriptor("fake-a"))
    service = CapabilityProbeService(default_ttl_seconds=60)
    ctx = context()
    results = await asyncio.gather(
        *[service.probe(fake, ctx, capability_id="synthesize.speech") for _ in range(8)]
    )
    assert len({id(item) for item in results}) == 1


def test_credential_store_exposes_metadata_only_and_supports_revoke_rotate() -> None:
    store = InMemoryCredentialStore()
    metadata = store.put("fake.api", "fake-a", "secret-value", "invoke")
    assert "secret-value" not in metadata.model_dump_json()
    assert store.get_secret("fake.api") == "secret-value"
    assert store.rotate("fake.api", "new-secret").status == "active"
    assert store.revoke("fake.api").status == "revoked"
    assert redact_sensitive("Authorization: Bearer secret-value") == "[REDACTED]"


def test_price_book_budget_and_rate_limit_are_deterministic() -> None:
    book = PriceBookV1(
        version="fake-1",
        effective_at=datetime(2026, 8, 11, tzinfo=UTC),
        lines=[
            PriceLineV1(
                provider_id="fake-a",
                capability_id="synthesize.speech",
                currency="USD",
                unit="request",
                unit_price_minor="0.25",
                price_book_version="fake-1",
            )
        ],
    )
    assert book.estimate("fake-a", "synthesize.speech", 4).unit_price_minor == 1
    ledger = BudgetLedger({"invocation": 5, "project": 10})
    assert ledger.reserve(4, scopes=("invocation", "project")).allowed
    assert not ledger.reserve(2, scopes=("invocation", "project")).allowed
    limiter = ProviderRateLimiter(capacity=1, refill_per_second=1)
    assert limiter.consume("fake-a", "fake.api", "synthesize.speech").allowed
    assert not limiter.consume("fake-a", "fake.api", "synthesize.speech").allowed


def test_policy_filters_regions_and_blocks_unsafe_failover() -> None:
    policy = ProviderPolicyV1(allowed_provider_ids=["fake-a"], allowed_regions=["CN"])
    evaluator = ProviderPolicyEvaluator(policy)
    assert evaluator.evaluate(
        descriptor("fake-a"), data_classification="sensitive", region="CN"
    ).allowed
    assert not evaluator.evaluate(
        descriptor("fake-b"), data_classification="sensitive", region="CN"
    ).allowed
    assert not failover_allowed(
        policy=policy,
        error_code="provider.timeout",
        error_retryable=True,
        billed_state="unknown",
        fixed_provider=False,
        region_would_expand=False,
        budget_would_increase=False,
    )


def test_artifact_publisher_validates_hash_size_and_safe_path(tmp_path: Path) -> None:
    publisher = ArtifactPublisher(tmp_path)
    staged = publisher.staging / "output.bin"
    staged.write_bytes(b"artifact")
    digest = "sha256:" + sha256(b"artifact").hexdigest()
    ref = publisher.publish(
        staged,
        project_id="project-a",
        logical_path="audio/output.bin",
        media_type="application/octet-stream",
        expected_sha256=digest,
        expected_size=8,
    )
    assert ref.object_id == digest
    with pytest.raises(ArtifactValidationError):
        publisher.publish(
            staged,
            project_id="project-a",
            logical_path="../escape.bin",
            media_type="application/octet-stream",
            expected_sha256=digest,
            expected_size=8,
        )


def test_provider_api_never_returns_credential_value() -> None:
    fake = DeterministicFakeProvider(descriptor("fake-a"))
    state = ProviderApiState(ProviderRegistry([fake.descriptor]), {"fake-a": fake})
    app = FastAPI()
    app.include_router(create_provider_router(state), prefix="/api")
    tenant = str(uuid4())
    with TestClient(app) as client:
        listed = client.get("/api/providers")
        assert listed.status_code == 200
        assert listed.json()[0]["provider_id"] == "fake-a"
        cached = client.get(
            "/api/providers", headers={"If-None-Match": listed.headers["etag"]}
        )
        assert cached.status_code == 304
        sample = client.post(
            "/api/providers/fake-a/probe",
            json={"tenant_id": tenant, "capability_id": "synthesize.speech", "mode": "sample"},
        )
        assert sample.status_code == 409
        policy = client.put(
            "/api/providers/projects/project-a/policy?tenant_id=" + tenant,
            json={"policy": {"allowed_provider_ids": ["fake-a"]}},
        )
        assert policy.status_code == 200
        assert "secret" not in policy.text.lower()
        stored = client.post(
            "/api/providers/credentials",
            json={
                "credential_ref": "fake.main",
                "provider_id": "fake-a",
                "secret": "top-secret",
                "scope": "tenant:test",
            },
        )
        assert stored.status_code == 201
        assert "top-secret" not in stored.text
        assert client.get("/api/providers/credentials").json()[0]["credential_ref"] == "fake.main"
        rotated = client.post(
            "/api/providers/credentials/fake.main/rotate",
            json={"secret": "rotated-secret"},
        )
        assert rotated.status_code == 200
        revoked = client.delete("/api/providers/credentials/fake.main")
        assert revoked.status_code == 200
        assert revoked.json()["status"] == "revoked"
        invoked = client.post(
            "/api/providers/fake-a/invoke",
            json={
                "tenant_id": tenant,
                "capability_id": "synthesize.speech",
                "expected_output_schema": "audio-v1",
                "input_refs": ["sha256:" + "a" * 64],
            },
        )
        assert invoked.status_code == 200
        operation_id = invoked.json()["operation_id"]
        cancelled = client.post(
            "/api/providers/fake-a/cancel",
            json={"operation_id": operation_id},
        )
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancel_requested"


def test_provider_api_applies_rate_limit_and_records_project_usage() -> None:
    fake = DeterministicFakeProvider(descriptor("fake-a"))
    state = ProviderApiState(
        ProviderRegistry([fake.descriptor]),
        {"fake-a": fake},
        rate_limiter=ProviderRateLimiter(capacity=1, refill_per_second=1),
    )
    app = FastAPI()
    app.include_router(create_provider_router(state), prefix="/api")
    tenant = str(uuid4())
    payload = {
        "tenant_id": tenant,
        "project_id": "project-a",
        "credential_ref": "fake.main",
        "capability_id": "synthesize.speech",
        "expected_output_schema": "audio-v1",
        "input_refs": ["sha256:" + "a" * 64],
    }
    with TestClient(app) as client:
        first = client.post("/api/providers/fake-a/invoke", json=payload)
        second = client.post("/api/providers/fake-a/invoke", json=payload)
        usage = client.get(f"/api/providers/projects/project-a/usage?tenant_id={tenant}")
    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) >= 1
    assert usage.json()["billed_minor"] == 1
