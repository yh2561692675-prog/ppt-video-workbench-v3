from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from workbench.main import create_app


def test_content_assist_routes_keep_ai_output_as_candidate(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path)) as client:
        created = client.post(
            "/api/ai/content-assist",
            json={"kind": "polish", "source_text": "这是旁白", "style": "neutral"},
        )
        assert created.status_code == 201, created.text
        candidate_id = created.json()["data"]["candidate_id"]
        assert created.json()["data"]["status"] == "candidate"
        accepted = client.post(f"/api/ai/content-assist/{candidate_id}/accept")
        assert accepted.status_code == 200
        assert accepted.json()["data"]["status"] == "accepted"
