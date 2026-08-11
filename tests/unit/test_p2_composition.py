from __future__ import annotations

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


def test_cloud_sync_flag_creates_only_the_opt_in_outbox(tmp_path: Path) -> None:
    composition = P2Composition.build(
        tmp_path,
        flags=P2FeatureFlags(cloud_sync_enabled=True),
    )
    assert composition.sync_client is not None
    assert (tmp_path / ".sync" / "outbox.db").exists()
