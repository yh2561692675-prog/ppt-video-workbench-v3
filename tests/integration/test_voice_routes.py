from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from workbench.main import create_app


def test_voice_authorization_and_revoke_routes_are_local_only(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path)) as client:
        granted = client.post(
            "/api/ai/voices/authorizations",
            json={
                "schema_version": 1,
                "subject": "self",
                "granted_by": "owner",
                "scopes": ["local_clone", "local_tts"],
                "source_audio_sha256": "a" * 64,
            },
        )
        assert granted.status_code == 201, granted.text
        authorization_id = granted.json()["data"]["authorization_id"]
        registered = client.post(
            "/api/ai/voices",
            json={
                "schema_version": 1,
                "voice_id": "owner-voice",
                "display_name": "Owner voice",
                "kind": "local_clone",
                "model_id": "local-clone",
                "model_revision": "r1",
                "authorization_id": authorization_id,
            },
        )
        assert registered.status_code == 201, registered.text
        assert registered.json()["data"]["remote_export_allowed"] is False
        revoked = client.post("/api/ai/voices/owner-voice/revoke")
        assert revoked.status_code == 200
        assert revoked.json()["data"]["status"] == "revoked"
