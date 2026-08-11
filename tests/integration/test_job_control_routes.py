from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from workbench.domain.enums import JobType
from workbench.jobs.repository import JobSpec
from workbench.main import create_app


def test_job_routes_expose_attempts_and_enforce_expected_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Enqueue persists a queued job only.  Attempt generation is a claim-side
    # effect, so disable the application worker to exercise route CAS without
    # a background claim changing the revision between requests.
    monkeypatch.setenv("WORKBENCH_ASYNC_RENDER_ENABLED", "false")
    app = create_app(tmp_path)
    project = app.state.project_service.create("durable job API")
    job = app.state.project_service.jobs.enqueue_or_get(
        JobSpec(project_id=project.id, job_type=JobType.RENDER_PREVIEW, cache_key="api-preview")
    ).record
    assert app.state.project_service.jobs.list_attempts(job.id) == []

    with TestClient(app) as client:
        listed = client.get(f"/api/projects/{project.id}/jobs")
        detail = client.get(f"/api/projects/{project.id}/jobs/{job.id}")
        conflict = client.post(
            f"/api/projects/{project.id}/jobs/{job.id}/actions",
            json={"action": "pause", "expected_revision": job.revision + 1},
        )
        paused = client.post(
            f"/api/projects/{project.id}/jobs/{job.id}/actions",
            json={"action": "pause", "expected_revision": job.revision},
        )

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["data"]] == [str(job.id)]
    assert detail.status_code == 200
    assert detail.json()["data"]["attempts"] == []
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "job_transition_conflict"
    assert paused.status_code == 200
    assert paused.json()["data"]["status"] == "paused"
