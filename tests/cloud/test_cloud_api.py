from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from workbench.contracts.p2_platform import canonical_sha256

from cloud_prototype.app import create_cloud_app


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
            },
            headers=headers,
        )
        assert executor.status_code == 201
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
