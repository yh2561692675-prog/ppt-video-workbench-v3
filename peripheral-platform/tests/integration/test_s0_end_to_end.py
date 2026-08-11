from __future__ import annotations

import hashlib
import time
from pathlib import Path

from fastapi.testclient import TestClient
from peripheral_contracts import JobEnvelope
from peripheral_host.api import create_internal_app


def test_s0_end_to_end(
    scheduler_bundle,
    job: JobEnvelope,
) -> None:
    scheduler, service, _, _ = scheduler_bundle
    client = TestClient(create_internal_app(service=service, scheduler=scheduler))
    request = job.model_copy(update={"parameters": {"text": "S0 acceptance"}})
    scheduler.start()
    try:
        submitted = client.post(
            "/internal/v1/jobs",
            json=request.model_dump(mode="json"),
        )
        assert submitted.status_code == 202
        job_id = submitted.json()["job_id"]
        deadline = time.monotonic() + 10
        current: dict[str, object] = {}
        while time.monotonic() < deadline:
            response = client.get(f"/internal/v1/jobs/{job_id}")
            current = response.json()
            if current["status"] in {"succeeded", "failed", "cancelled"}:
                break
            time.sleep(0.02)

        assert current["status"] == "succeeded"
        artifacts = client.get(f"/internal/v1/jobs/{job_id}/artifacts").json()
        assert len(artifacts) == 1
        artifact = artifacts[0]
        artifact_path = service.workspace_root / Path(artifact["relative_path"])
        payload = artifact_path.read_bytes()
        assert payload == b"S0 acceptance"
        assert hashlib.sha256(payload).hexdigest() == artifact["sha256"]
        assert len(service.repositories.events.list_for_job(request.job_id)) >= 5
    finally:
        scheduler.stop(grace_seconds=2)
