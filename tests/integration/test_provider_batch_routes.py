from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from workbench.main import create_app


def test_provider_batch_route_persists_opt_in_job_state(tmp_path: Path) -> None:
    project_id = str(uuid4())
    revision_id = str(uuid4())
    pages = [str(uuid4()), str(uuid4())]
    with TestClient(create_app(tmp_path)) as client:
        created = client.post(
            "/api/providers/batches",
            json={
                "provider_id": "heygen",
                "operation_kind": "tts",
                "project_id": project_id,
                "revision_id": revision_id,
                "page_ids": pages,
            },
        )
        assert created.status_code == 201, created.text
        job_id = created.json()["data"]["job_id"]
        resumed = client.post(f"/api/providers/batches/{job_id}/resume")
        assert resumed.status_code == 200
        assert len(resumed.json()["data"]) == 2

    with TestClient(create_app(tmp_path)) as restarted:
        fetched = restarted.get(f"/api/providers/batches/{job_id}")
        assert fetched.status_code == 200
        assert fetched.json()["data"]["status"] == "queued"
