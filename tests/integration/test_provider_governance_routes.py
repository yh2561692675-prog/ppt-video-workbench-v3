from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from workbench.main import create_app


def test_unknown_billing_can_only_be_closed_by_explicit_reconcile(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    with TestClient(app) as client:
        decision = app.state.provider_governance.authorize(
            operation_id=uuid4(),
            provider_id="remote-tts",
            credential_ref="credential.ref",
            capability_id="synthesize.speech",
            estimated_cost_minor=10,
            scopes=("operation",),
            price_book_version="test",
        )
        assert decision.reservation_id is not None
        app.state.provider_governance.complete(
            decision.reservation_id, billing_state="unknown"
        )
        response = client.post(
            f"/api/providers/governance/{decision.reservation_id}/reconcile",
            json={"billed_cost_minor": 7},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == "committed"
