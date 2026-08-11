from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from workbench.contracts.p2_platform import canonical_sha256

from cloud_prototype.app import CloudProductionEvidence, create_cloud_app


def _operation(workspace_id: str, project_id: str, revision_id: str) -> dict[str, object]:
    payload = {"title": "updated"}
    return {
        "schema_version": 1,
        "operation_id": str(uuid4()),
        "idempotency_key": str(uuid4()),
        "attempt_id": str(uuid4()),
        "workspace_id": workspace_id,
        "project_id": project_id,
        "base_revision_id": revision_id,
        "client_id": str(uuid4()),
        "client_sequence": 1,
        "kind": "project.metadata.set",
        "payload": payload,
        "payload_sha256": canonical_sha256(payload),
        "created_at": "2026-08-11T00:00:00Z",
    }


def test_cloud_prototype_enforces_tenant_ownership_and_idempotent_revisions(tmp_path: Path) -> None:
    app = create_cloud_app(tmp_path / "control.db", tmp_path / "objects")
    with TestClient(app) as client:
        headers = {"X-Actor-ID": "alice"}
        workspace = client.post("/v1/workspaces", json={"name": "Team"}, headers=headers).json()
        workspace_id = workspace["workspace_id"]
        project = client.post(
            f"/v1/workspaces/{workspace_id}/projects",
            json={"name": "Course", "manifest": {"pages": []}},
            headers=headers,
        ).json()
        project_id = project["project_id"]
        revision_id = project["current_revision_id"]
        member = client.post(
            f"/v1/workspaces/{workspace_id}/members",
            json={"actor_id": "bob", "role": "reviewer"},
            headers=headers,
        )
        assert member.status_code == 201
        assert (
            client.get(
                f"/v1/workspaces/{workspace_id}/members", headers={"X-Actor-ID": "bob"}
            ).status_code
            == 200
        )
        revision = client.get(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/revisions/{revision_id}",
            headers=headers,
        )
        assert revision.status_code == 200
        assert revision.headers["etag"].startswith("sha256:")
        operation = _operation(workspace_id, project_id, revision_id)
        first = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/operations",
            json=operation,
            headers=headers,
        )
        assert first.status_code == 201
        stale = _operation(workspace_id, project_id, revision_id)
        conflict = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/operations",
            json=stale,
            headers=headers,
        )
        assert conflict.status_code == 409
        second = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/operations",
            json=operation,
            headers=headers,
        )
        assert second.status_code == 201
        assert second.json()["revision"]["revision_id"] == first.json()["revision"]["revision_id"]
        hidden = client.get(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}",
            headers={"X-Actor-ID": "mallory"},
        )
        assert hidden.status_code == 404


def test_cloud_revisions_reject_host_paths_and_credentials(tmp_path: Path) -> None:
    app = create_cloud_app(tmp_path / "control.db", tmp_path / "objects")
    with TestClient(app) as client:
        headers = {"X-Actor-ID": "alice"}
        workspace_id = client.post("/v1/workspaces", json={"name": "Team"}, headers=headers).json()[
            "workspace_id"
        ]
        rejected_project = client.post(
            f"/v1/workspaces/{workspace_id}/projects",
            json={"name": "Unsafe", "manifest": {"source_path": "C:\\secret\\deck.pptx"}},
            headers=headers,
        )
        assert rejected_project.status_code == 422
        project = client.post(
            f"/v1/workspaces/{workspace_id}/projects",
            json={"name": "Safe", "manifest": {"pages": []}},
            headers=headers,
        ).json()
        payload = {"api_key": "must-not-persist"}
        operation = _operation(workspace_id, project["project_id"], project["current_revision_id"])
        operation["payload"] = payload
        operation["payload_sha256"] = canonical_sha256(payload)
        response = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}/operations",
            json=operation,
            headers=headers,
        )
        assert response.status_code == 422
        assert response.json()["detail"] == "sensitive_field_rejected"


def test_cloud_prototype_validates_objects_and_supports_review_lease_job(tmp_path: Path) -> None:
    app = create_cloud_app(tmp_path / "control.db", tmp_path / "objects")
    with TestClient(app) as client:
        headers = {"X-Actor-ID": "alice"}
        workspace_id = client.post("/v1/workspaces", json={"name": "Team"}, headers=headers).json()[
            "workspace_id"
        ]
        project = client.post(
            f"/v1/workspaces/{workspace_id}/projects", json={"name": "Course"}, headers=headers
        ).json()
        project_id, revision_id = project["project_id"], project["current_revision_id"]
        object_id = "sha256:" + hashlib.sha256(b"asset").hexdigest()
        upload = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/objects/uploads",
            json={
                "object": {
                    "object_id": object_id,
                    "size_bytes": 5,
                    "media_type": "image/png",
                    "classification": "internal",
                }
            },
            headers=headers,
        )
        assert upload.status_code == 201
        invalid_complete = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/objects/uploads/{upload.json()['upload_id']}/complete",
            json={"parts": [{"part_number": 1, "etag": "etag", "size_bytes": 4}]},
            headers=headers,
        )
        assert invalid_complete.status_code == 422
        assert invalid_complete.json()["detail"] == "upload_size_mismatch"
        completed = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/objects/uploads/{upload.json()['upload_id']}/complete",
            json={"parts": [{"part_number": 1, "etag": "etag"}]},
            headers=headers,
        )
        assert completed.status_code == 201
        with sqlite3.connect(tmp_path / "control.db") as db:
            stored_path = db.execute("SELECT path FROM objects").fetchone()[0]
        assert stored_path == f"{project_id}/{object_id.removeprefix('sha256:')}"
        assert str(tmp_path) not in stored_path
        assert (
            client.post(
                f"/v1/workspaces/{workspace_id}/projects/{project_id}/objects/{object_id}/download",
                headers=headers,
            ).status_code
            == 200
        )
        comment = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/comments",
            json={"body": "Review", "anchor": {"revision_id": revision_id}},
            headers=headers,
        )
        assert comment.status_code == 201
        review = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/reviews",
            json={"revision_id": revision_id, "decision": "approved"},
            headers=headers,
        )
        assert review.status_code == 201
        lease = client.put(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/lease",
            json={"client_id": str(uuid4()), "requested_ttl_seconds": 60},
            headers=headers,
        )
        assert lease.status_code == 200
        executor = client.post(
            f"/v1/workspaces/{workspace_id}/executors",
            json={
                "platform": "windows",
                "capabilities": ["render"],
                "region": "local",
                "capability_snapshot": {
                    "fingerprint": "sha256:" + "a" * 64,
                    "tools": ["media.encode"],
                },
            },
            headers=headers,
        )
        assert executor.status_code == 201
        assert executor.json()["capability_snapshot"]["fingerprint"] == "sha256:" + "a" * 64
        assert (
            client.get(f"/v1/workspaces/{workspace_id}/executors", headers=headers).json()["items"][
                0
            ]["status"]
            == "active"
        )
        job = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/jobs",
            json={"revision_id": revision_id, "kind": "render"},
            headers=headers,
        )
        assert job.status_code == 202
        assert job.json()["status"] == "dispatched"
        assert job.json()["executor_id"] == executor.json()["executor_id"]
        job_id = job.json()["job_id"]
        assert client.get(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/jobs", headers=headers
        ).json()["items"]
        assert (
            client.get(
                f"/v1/workspaces/{workspace_id}/projects/{project_id}/jobs/{job_id}",
                headers=headers,
            ).status_code
            == 200
        )
        assert (
            client.delete(
                f"/v1/workspaces/{workspace_id}/projects/{project_id}/jobs/{job_id}",
                headers=headers,
            ).json()["status"]
            == "cancelled"
        )


def test_cloud_production_auth_mode_fails_closed_without_oidc(tmp_path: Path) -> None:
    app = create_cloud_app(
        tmp_path / "control.db",
        tmp_path / "objects",
        auth_mode="production",
    )
    with TestClient(app) as client:
        assert client.get("/v1/health").json()["auth_mode"] == "production"
        response = client.post("/v1/workspaces", json={"name": "Blocked"})
        assert response.status_code == 503


def test_cloud_production_gate_requires_external_evidence(tmp_path: Path) -> None:
    app = create_cloud_app(
        tmp_path / "control.db",
        tmp_path / "objects",
        auth_mode="production",
        oidc_issuer="https://issuer.invalid",
        oidc_audience="workbench",
        production_evidence=CloudProductionEvidence(oidc_validation=True),
    )
    with TestClient(app) as client:
        assert client.get("/v1/health").json()["production_gate"] == "blocked"
        response = client.post("/v1/workspaces", json={"name": "Blocked"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "production_gate_incomplete"


def test_cloud_object_declaration_rejects_invalid_hash_and_restricted_data(tmp_path: Path) -> None:
    app = create_cloud_app(tmp_path / "control.db", tmp_path / "objects")
    with TestClient(app) as client:
        headers = {"X-Actor-ID": "alice"}
        workspace_id = client.post("/v1/workspaces", json={"name": "Team"}, headers=headers).json()[
            "workspace_id"
        ]
        project_id = client.post(
            f"/v1/workspaces/{workspace_id}/projects",
            json={"name": "Course"},
            headers=headers,
        ).json()["project_id"]
        invalid = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/objects/uploads",
            json={"object": {"object_id": "sha256:../escape", "size_bytes": 1}},
            headers=headers,
        )
        assert invalid.status_code == 422
        restricted = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/objects/uploads",
            json={
                "object": {
                    "object_id": "sha256:" + "a" * 64,
                    "size_bytes": 1,
                    "media_type": "application/octet-stream",
                    "classification": "restricted",
                }
            },
            headers=headers,
        )
        assert restricted.status_code == 422


def test_cloud_executor_result_is_hash_checked_and_idempotent(tmp_path: Path) -> None:
    app = create_cloud_app(tmp_path / "control.db", tmp_path / "objects")
    with TestClient(app) as client:
        headers = {"X-Actor-ID": "alice"}
        workspace_id = client.post("/v1/workspaces", json={"name": "Team"}, headers=headers).json()[
            "workspace_id"
        ]
        project = client.post(
            f"/v1/workspaces/{workspace_id}/projects",
            json={"name": "Course"},
            headers=headers,
        ).json()
        executor = client.post(
            f"/v1/workspaces/{workspace_id}/executors",
            json={"platform": "windows", "capabilities": ["render"], "region": "local"},
            headers=headers,
        ).json()
        job = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}/jobs",
            json={
                "revision_id": project["current_revision_id"],
                "kind": "render",
                "fingerprints": {
                    "provider_policy": "sha256:" + "1" * 64,
                    "platform": "sha256:" + "2" * 64,
                    "runtime": "sha256:" + "3" * 64,
                    "input": "sha256:" + "4" * 64,
                },
            },
            headers=headers,
        ).json()
        fingerprints = job["fingerprints"]
        result = {"media_type": "video/mp4", "duration_ms": 1000}
        output_object = "sha256:" + "b" * 64
        result_url = (
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}"
            f"/jobs/{job['job_id']}/result"
        )
        unowned = client.post(
            result_url,
            json={
                "attempt_id": str(uuid4()),
                "executor_id": executor["executor_id"],
                "status": "completed",
                "result": result,
                "result_sha256": canonical_sha256(result),
                "output_refs": ["artifact://" + output_object],
                "fingerprints": fingerprints,
            },
            headers=headers,
        )
        assert unowned.status_code == 422
        assert unowned.json()["detail"] == "result_object_not_owned"
        upload = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}/objects/uploads",
            json={
                "object": {
                    "object_id": output_object,
                    "size_bytes": 0,
                    "media_type": "video/mp4",
                    "classification": "internal",
                }
            },
            headers=headers,
        )
        assert upload.status_code == 201
        assert client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}"
            f"/objects/uploads/{upload.json()['upload_id']}/complete",
            json={"parts": [{"part_number": 1, "etag": "empty"}]},
            headers=headers,
        ).status_code == 201
        report = {
            "attempt_id": str(uuid4()),
            "executor_id": executor["executor_id"],
            "status": "completed",
            "result": result,
            "result_sha256": canonical_sha256(result),
            "output_refs": ["artifact://" + output_object],
            "fingerprints": fingerprints,
        }
        completed = client.post(result_url, json=report, headers=headers)
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        repeated = client.post(result_url, json=report, headers=headers)
        assert repeated.status_code == 200
        job_after = client.get(
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}/jobs/{job['job_id']}",
            headers=headers,
        ).json()
        assert job_after["result"]["result_sha256"] == report["result_sha256"]
        assert job_after["result"]["output_refs"] == report["output_refs"]
        assert job_after["result"]["fingerprints"] == fingerprints

        mismatch = dict(report)
        mismatch["attempt_id"] = str(uuid4())
        mismatch["fingerprints"] = {**fingerprints, "runtime": "sha256:" + "9" * 64}
        rejected = client.post(result_url, json=mismatch, headers=headers)
        assert rejected.status_code == 422
        assert rejected.json()["detail"] == "job_fingerprint_mismatch"


def test_cloud_job_dispatch_matches_required_executor_capabilities(tmp_path: Path) -> None:
    app = create_cloud_app(tmp_path / "control.db", tmp_path / "objects")
    with TestClient(app) as client:
        headers = {"X-Actor-ID": "alice"}
        workspace_id = client.post("/v1/workspaces", json={"name": "Team"}, headers=headers).json()[
            "workspace_id"
        ]
        project = client.post(
            f"/v1/workspaces/{workspace_id}/projects",
            json={"name": "Course"},
            headers=headers,
        ).json()
        unsafe_executor = client.post(
            f"/v1/workspaces/{workspace_id}/executors",
            json={
                "platform": "windows",
                "capabilities": ["render"],
                "region": "local",
                "capability_snapshot": {
                    "tools": [{"executable_ref": r"C:\secret\ffmpeg.exe"}]
                },
            },
            headers=headers,
        )
        assert unsafe_executor.status_code == 422
        client.post(
            f"/v1/workspaces/{workspace_id}/executors",
            json={
                "platform": "windows",
                "capabilities": ["render"],
                "region": "local",
                "capability_snapshot": {"fingerprint": "sha256:" + "b" * 64},
            },
            headers=headers,
        )
        capable = client.post(
            f"/v1/workspaces/{workspace_id}/executors",
            json={
                "platform": "windows",
                "capabilities": ["render", "gpu.nvidia"],
                "region": "local",
            },
            headers=headers,
        ).json()
        job = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}/jobs",
            json={
                "revision_id": project["current_revision_id"],
                "kind": "render",
                "parameters": {"required_capabilities": ["gpu.nvidia"]},
            },
            headers=headers,
        ).json()
    assert job["status"] == "dispatched"
    assert job["executor_id"] == capable["executor_id"]
