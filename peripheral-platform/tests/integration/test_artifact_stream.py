from __future__ import annotations

import hashlib
from uuid import uuid4

from fastapi.testclient import TestClient
from peripheral_contracts import JobResult, OutputArtifact
from peripheral_host.api import create_internal_app


def _publish_sample_artifact(scheduler_bundle, job):
    scheduler, service, repositories, clock = scheduler_bundle
    service.submit_job(job)
    record = service.claim_next(clock.now())
    assert record is not None
    attempt_root = service.workspace_root / "projects" / str(job.project_id) / "state" / "attempts"
    attempt = repositories.attempts.create(job.job_id, 1, attempt_root)
    attempt.root.mkdir(parents=True, exist_ok=True)
    payload = b"streamed artifact\n"
    staged = attempt.root / "result.json"
    staged.write_bytes(payload)
    result = JobResult(
        schema_version="1.0",
        job_id=job.job_id,
        outcome="succeeded",
        outputs=(
            OutputArtifact(
                logical_name="sample-result",
                kind="json",
                staged_path="result.json",
                size_bytes=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
            ),
        ),
    )
    service.complete_attempt(job.job_id, attempt.attempt_id, result)
    artifact = repositories.artifacts.list_for_job(job.job_id)[0]
    return service, artifact, payload


def test_artifact_content_stream_is_verified_and_hides_physical_path(scheduler_bundle, job) -> None:
    service, artifact, payload = _publish_sample_artifact(scheduler_bundle, job)
    client = TestClient(create_internal_app(service=service, scheduler=scheduler_bundle[0]))

    response = client.get(
        f"/internal/v1/jobs/{job.job_id}/artifacts/{artifact.artifact_id}/content"
    )

    assert response.status_code == 200
    assert response.content == payload
    assert response.headers["content-length"] == str(len(payload))
    assert response.headers["digest"] == f"sha-256={artifact.sha256}"
    assert str(service.workspace_root) not in response.text
    assert "relative_path" not in response.text


def test_artifact_content_rejects_artifact_from_another_job(scheduler_bundle, job) -> None:
    service, artifact, _ = _publish_sample_artifact(scheduler_bundle, job)
    client = TestClient(create_internal_app(service=service, scheduler=scheduler_bundle[0]))

    response = client.get(f"/internal/v1/jobs/{uuid4()}/artifacts/{artifact.artifact_id}/content")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"
