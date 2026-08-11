from __future__ import annotations

from itertools import product
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from workbench.p2 import P2Composition, P2FeatureFlags


def test_flags_are_off_by_default_and_do_not_create_platform_services(tmp_path: Path) -> None:
    composition = P2Composition.build(tmp_path, flags=P2FeatureFlags())
    assert composition.platform is None
    assert composition.provider_state is None
    assert composition.sync_client is None


def test_enabled_composition_is_explicit_and_provider_routes_are_opt_in(tmp_path: Path) -> None:
    def handler(_: object) -> str:
        return "injected"
    composition = P2Composition.build(
        tmp_path,
        flags=P2FeatureFlags(provider_platform_enabled=True, platform_services_enabled=True),
        provider_handlers={"builtin-llm": handler},
    )
    app = FastAPI()
    composition.install(app)
    assert composition.platform is not None
    assert app.state.p2_feature_flags.provider_platform_enabled is True
    with TestClient(app) as client:
        response = client.get("/api/providers")
    assert response.status_code == 200
    assert {item["provider_id"] for item in response.json()} == {
        "builtin-llm",
        "builtin-asr",
        "builtin-tts",
        "builtin-avatar",
        "builtin-ocr",
        "builtin-renderer",
    }
    assert composition.provider_state is not None
    assert composition.provider_state.adapters["builtin-llm"].handler is handler  # type: ignore[attr-defined]
    diagnostics = client.get("/api/p2/diagnostics")
    assert diagnostics.status_code == 200
    assert "secret" not in diagnostics.text.lower()
    payload = diagnostics.json()
    assert payload["platform_details"]["office"]["network_access"] is False
    assert payload["platform_details"]["office"]["macro_execution"] is False
    assert str(tmp_path) not in diagnostics.text
    assert all(
        not str(item.get("executable_ref", "")).startswith(("/", "\\"))
        for item in payload["platform"]["tools"]
    )
    assert payload["privacy_scan"] == {
        "status": "pass",
        "finding_codes": [],
        "finding_count": 0,
    }
    assert payload["cloud"] == {
        "status": "disabled",
        "production_auth": "not_configured",
    }
    assert payload["executor"] == {
        "status": "not_registered",
        "capability_labels": [],
    }


def test_cloud_sync_flag_creates_only_the_opt_in_outbox(tmp_path: Path) -> None:
    composition = P2Composition.build(
        tmp_path,
        flags=P2FeatureFlags(cloud_sync_enabled=True),
    )
    assert composition.sync_client is not None
    assert (tmp_path / ".sync" / "outbox.db").exists()


def test_provider_flag_alone_uses_non_persistent_fake_credentials(tmp_path: Path) -> None:
    composition = P2Composition.build(
        tmp_path,
        flags=P2FeatureFlags(provider_platform_enabled=True),
    )
    assert composition.platform is None
    assert composition.provider_state is not None
    app = FastAPI()
    composition.install(app)
    with TestClient(app) as client:
        response = client.post(
            "/api/providers/credentials",
            json={
                "credential_ref": "fake.main",
                "provider_id": "builtin-llm",
                "secret": "memory-only",
                "scope": "test",
            },
        )
        listed = client.get("/api/providers/credentials")
    assert response.status_code == 201
    assert listed.status_code == 200
    assert listed.json()[0]["credential_ref"] == "fake.main"
    assert not (tmp_path / "credentials.json").exists()


def test_all_feature_flag_combinations_are_independent(tmp_path: Path) -> None:
    for provider_enabled, platform_enabled, cloud_enabled in product(
        (False, True), repeat=3
    ):
        workspace = tmp_path / (
            f"p{int(provider_enabled)}-x{int(platform_enabled)}-c{int(cloud_enabled)}"
        )
        composition = P2Composition.build(
            workspace,
            flags=P2FeatureFlags(
                provider_platform_enabled=provider_enabled,
                platform_services_enabled=platform_enabled,
                cloud_sync_enabled=cloud_enabled,
            ),
        )
        assert (composition.provider_state is not None) is provider_enabled
        assert (composition.platform is not None) is platform_enabled
        assert (composition.sync_client is not None) is cloud_enabled
        assert (workspace / ".sync" / "outbox.db").exists() is cloud_enabled
        if provider_enabled and platform_enabled:
            assert composition.provider_state is not None
            assert composition.platform is not None
            assert composition.provider_state.credential_store is composition.platform.credentials


def test_diagnostics_export_is_selective_and_privacy_scanned(tmp_path: Path) -> None:
    composition = P2Composition.build(
        tmp_path,
        flags=P2FeatureFlags(
            provider_platform_enabled=True,
            platform_services_enabled=True,
            cloud_sync_enabled=True,
        ),
    )
    app = FastAPI()
    composition.install(app)
    with TestClient(app) as client:
        response = client.get(
            "/api/p2/diagnostics/export",
            params=[("sections", "providers"), ("sections", "sync")],
        )
    assert response.status_code == 200
    assert response.headers["content-disposition"] == (
        'attachment; filename="p2-diagnostics-safe-summary.json"'
    )
    payload = response.json()
    assert set(payload) == {
        "schema_version",
        "generated_at",
        "providers",
        "sync",
        "privacy_scan",
    }
    assert payload["privacy_scan"] == {
        "status": "pass",
        "finding_codes": [],
        "finding_count": 0,
    }
    assert str(tmp_path) not in response.text
    assert "secret" not in response.text.lower()
