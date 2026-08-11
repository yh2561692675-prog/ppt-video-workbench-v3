from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from workbench.api.secure_updates import create_secure_updates_router
from workbench.updates.secure import (
    HttpResponse,
    SecureUpdateClient,
    TrustedKey,
    TrustedRoot,
)


def test_secure_update_routes_expose_state_and_reject_untrusted_url(tmp_path: Path) -> None:
    client = SecureUpdateClient(
        tmp_path,
        trusted_root=TrustedRoot(
            version=1,
            threshold=1,
            keys=[TrustedKey(key_id="root-1", public_key="unused")],
        ),
        verifier=lambda _payload, _signature, _key: True,
        transport=lambda _url, _headers: HttpResponse(status=404, body=b""),
        now=lambda: datetime(2026, 8, 10, tzinfo=UTC),
    )
    app = FastAPI()
    app.include_router(create_secure_updates_router(client))

    with TestClient(app) as http:
        state = http.get("/api/updates/secure")
        assert state.status_code == 200
        assert state.json()["data"]["status"] == "idle"
        check = http.post(
            "/api/updates/secure/check",
            params={"metadata_url": "http://updates.example"},
        )
        assert check.status_code == 409
        assert check.json()["detail"]["code"] == "update_url_not_https"
