from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from workbench.main import create_app
from workbench_peripheral_adapter.dto import (
    ArtifactDto,
    JobStatusDto,
    SubmitJobResultDto,
)


class FakeClient:
    enabled = True

    def __init__(self) -> None:
        self.request = None
        self.payload = b""
        self.succeeded = False

    def probe(self):
        return True

    def submit_job(self, request):
        self.request = request
        return SubmitJobResultDto(job_id=request.job_id, status="queued", created=True)

    def get_job_status(self, job_id):
        assert self.request is not None
        return JobStatusDto(
            schema_version="1.0",
            job_id=job_id,
            project_id=self.request.project_id,
            job_type=self.request.job_type,
            status="succeeded" if self.succeeded else "queued",
            attempt_count=1 if self.succeeded else 0,
            progress=100 if self.succeeded else 0,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    def list_artifacts(self, job_id):
        assert self.request is not None
        return (
            ArtifactDto(
                artifact_id=uuid4(),
                job_id=job_id,
                project_id=self.request.project_id,
                logical_name="business-result",
                kind="json",
                version=1,
                size_bytes=len(self.payload),
                sha256=hashlib.sha256(self.payload).hexdigest(),
                verified_at=datetime.now(UTC),
                is_current=True,
            ),
        )

    def stream_artifact(self, job_id, artifact_id):
        yield self.payload


def test_s1_job_route_returns_execution_mode(tmp_path) -> None:
    client = TestClient(create_app(tmp_path, peripheral_client=FakeClient()))
    project_id = client.post("/api/projects", json={"name": "S1 route"}).json()["data"]["id"]
    response = client.post(
        f"/api/projects/{project_id}/s1/jobs/document.extract",
        json={
            "module_id": "P04",
            "requested_by": "test",
            "parameters": {"language": "zh"},
        },
    )
    assert response.status_code == 202
    assert response.json()["execution"] == "peripheral"


def test_s1_route_rejects_module_job_type_mismatch(tmp_path) -> None:
    client = TestClient(create_app(tmp_path, peripheral_client=FakeClient()))
    project_id = client.post("/api/projects", json={"name": "S1 mismatch"}).json()["data"]["id"]

    response = client.post(
        f"/api/projects/{project_id}/s1/jobs/video.render",
        json={"module_id": "P04", "requested_by": "test", "parameters": {}},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "s1_job_type_mismatch"


def test_s1_status_poll_reconciles_successful_result(tmp_path) -> None:
    fake = FakeClient()
    client = TestClient(create_app(tmp_path, peripheral_client=fake))
    project = client.post("/api/projects", json={"name": "S1 reconcile"}).json()["data"]
    project_id = project["id"]
    submitted = client.post(
        f"/api/projects/{project_id}/s1/jobs/quality.verify",
        json={"module_id": "P12", "requested_by": "test", "parameters": {}},
    )
    job_id = submitted.json()["job_id"]
    assert fake.request is not None
    fake.payload = json.dumps(
        {
            "schema_version": "1.0",
            "module_id": "P12",
            "job_type": "quality.verify",
            "project_id": project_id,
            "project_revision": 1,
            "input_fingerprint": fake.request.parameters["input_fingerprint"],
            "cache_key": "b" * 64,
            "result_type": "quality_report",
            "payload": {"decision": "blocked", "reasons": ["preflight_blocked"]},
            "artifacts": [],
        }
    ).encode()
    fake.succeeded = True

    status = client.get(f"/api/projects/{project_id}/s1/jobs/{job_id}")

    assert status.status_code == 200
    assert status.json()["projection"]["status"] == "applied"
    assert (tmp_path / project["project_dir"] / "s1-quality-report.json").is_file()
