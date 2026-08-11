from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from workbench.domain.models import ProjectManifest
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
        self.artifact_payload = b"quality artifact"
        self.business_artifact_id = None
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
        business = ArtifactDto(
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
        )
        self.business_artifact_id = business.artifact_id
        artifact_sha = hashlib.sha256(self.artifact_payload).hexdigest()
        return (
            business,
            ArtifactDto(
                artifact_id=uuid4(),
                job_id=job_id,
                project_id=self.request.project_id,
                logical_name="quality-report-json",
                kind="json",
                version=1,
                size_bytes=len(self.artifact_payload),
                sha256=artifact_sha,
                verified_at=datetime.now(UTC),
                is_current=True,
            ),
            ArtifactDto(
                artifact_id=uuid4(),
                job_id=job_id,
                project_id=self.request.project_id,
                logical_name="quality-report-md",
                kind="markdown",
                version=1,
                size_bytes=len(self.artifact_payload),
                sha256=artifact_sha,
                verified_at=datetime.now(UTC),
                is_current=True,
            ),
        )

    def stream_artifact(self, job_id, artifact_id):
        yield self.payload if artifact_id == self.business_artifact_id else self.artifact_payload


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
    artifact_sha = hashlib.sha256(fake.artifact_payload).hexdigest()
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
            "payload": {
                "automated_passed": False,
                "checks": [{"code": "preflight", "passed": False}],
                "package_sha256": "a" * 64,
                "generated_at": datetime.now(UTC).isoformat(),
                "artifacts": [
                    {
                        "logical_name": "quality-report-json",
                        "relative_path": "08_输出/验收/quality-report.json",
                        "size_bytes": len(fake.artifact_payload),
                        "sha256": artifact_sha,
                    },
                    {
                        "logical_name": "quality-report-md",
                        "relative_path": "08_输出/验收/quality-report.md",
                        "size_bytes": len(fake.artifact_payload),
                        "sha256": artifact_sha,
                    },
                ],
            },
            "artifacts": [
                {
                    "logical_name": "quality-report-json",
                    "kind": "json",
                    "size_bytes": len(fake.artifact_payload),
                    "sha256": artifact_sha,
                },
                {
                    "logical_name": "quality-report-md",
                    "kind": "markdown",
                    "size_bytes": len(fake.artifact_payload),
                    "sha256": artifact_sha,
                },
            ],
        }
    ).encode()
    fake.succeeded = True

    status = client.get(f"/api/projects/{project_id}/s1/jobs/{job_id}")

    assert status.status_code == 200
    assert status.json()["projection"]["status"] == "applied"
    manifest = ProjectManifest.model_validate_json(
        (tmp_path / project["project_dir"] / "project.json").read_text(encoding="utf-8")
    )
    assert manifest.audit_log[-1].action == "quality_verification_completed"
