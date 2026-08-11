from __future__ import annotations

import hashlib
import re
import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from workbench.contracts.p2_platform import canonical_sha256

from cloud_prototype.app import CloudProductionEvidence, CloudRepository, create_cloud_app

_PROVIDER_POLICY_SHA256 = "sha256:" + "1" * 64
_RUNTIME_IMAGE_SHA256 = "sha256:" + "3" * 64


def _idempotent(headers: dict[str, str]) -> dict[str, str]:
    return {**headers, "Idempotency-Key": str(uuid4())}


def _remote_job_request(revision_id: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "revision_id": revision_id,
        "kind": "render",
        "provider_policy_sha256": _PROVIDER_POLICY_SHA256,
        "provider_budget": {
            "schema_version": 1,
            "timeout_ms": 120_000,
            "max_attempts": 2,
            "max_input_bytes": 1_073_741_824,
            "max_output_bytes": 4_294_967_296,
            "max_cost_minor": 10_000,
        },
        "provider_cost_estimate_minor": 1_000,
        "runtime_image_sha256": _RUNTIME_IMAGE_SHA256,
        "fingerprints": {
            "provider_policy": _PROVIDER_POLICY_SHA256,
            "platform": "sha256:" + "2" * 64,
            "runtime": _RUNTIME_IMAGE_SHA256,
            "input": "sha256:" + "4" * 64,
        },
    }
    payload.update(overrides)
    return payload


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


def test_cloud_database_migrations_are_versioned_and_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "control.db"
    create_cloud_app(db_path, tmp_path / "objects")
    create_cloud_app(db_path, tmp_path / "objects")

    with sqlite3.connect(db_path) as db:
        rows = db.execute(
            "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
        ).fetchall()
    assert [(row[0], row[1]) for row in rows] == [
        (1, "0001_initial"),
        (2, "0002_identity_control"),
        (3, "0003_collaboration_integrity"),
        (4, "0004_remote_job_attempts"),
        (5, "0005_offline_sync_conflicts"),
        (6, "0006_remote_job_provider_budget"),
    ]
    assert all(re.fullmatch(r"sha256:[0-9a-f]{64}", row[2]) for row in rows)


def test_cloud_database_rejects_changed_applied_migration(tmp_path: Path) -> None:
    migration_root = tmp_path / "migrations"
    migration_root.mkdir()
    source = (
        Path(__file__).resolve().parents[2]
        / "cloud_prototype"
        / "migrations"
        / "0001_initial.sql"
    )
    copied = migration_root / source.name
    migration_text = source.read_text(encoding="utf-8")
    copied.write_text(migration_text, encoding="utf-8", newline="\n")
    db_path = tmp_path / "control.db"
    CloudRepository(db_path, tmp_path / "objects", migration_root=migration_root)
    copied.write_text(migration_text, encoding="utf-8", newline="\r\n")
    CloudRepository(db_path, tmp_path / "objects", migration_root=migration_root)
    copied.write_text(
        migration_text + "\n-- changed after application\n", encoding="utf-8", newline="\n"
    )

    with pytest.raises(RuntimeError, match="migration checksum mismatch"):
        CloudRepository(db_path, tmp_path / "objects", migration_root=migration_root)


def test_cloud_database_upgrades_legacy_executor_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "control.db"
    with sqlite3.connect(db_path) as db:
        db.executescript(
            """
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY, project_id TEXT NOT NULL, revision_id TEXT NOT NULL,
                actor_id TEXT NOT NULL, kind TEXT NOT NULL, parameters_json TEXT NOT NULL,
                status TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE job_results (
                attempt_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, status TEXT NOT NULL,
                result_sha256 TEXT NOT NULL, result_json TEXT NOT NULL, created_at TEXT NOT NULL
            );
            CREATE TABLE executors (
                id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL, actor_id TEXT NOT NULL,
                platform TEXT NOT NULL, capabilities_json TEXT NOT NULL, region TEXT NOT NULL,
                status TEXT NOT NULL, expires_at TEXT NOT NULL
            );
            """
        )

    CloudRepository(db_path, tmp_path / "objects")
    with sqlite3.connect(db_path) as db:
        job_columns = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
        result_columns = {row[1] for row in db.execute("PRAGMA table_info(job_results)")}
        executor_columns = {row[1] for row in db.execute("PRAGMA table_info(executors)")}
        operation_columns = {row[1] for row in db.execute("PRAGMA table_info(operations)")}
        conflict_tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_conflicts'"
            )
        }
    assert {
        "executor_id",
        "fingerprints_json",
        "attempt_id",
        "lease_id",
        "lease_expires_at",
        "attempt_token_hash",
        "provider_policy_sha256",
        "provider_budget_json",
        "provider_cost_estimate_minor",
        "runtime_image_sha256",
        "required_capabilities_json",
        "idempotency_key",
    } <= job_columns
    assert {
        "output_refs_json",
        "fingerprints_json",
        "result_schema_version",
        "output_media_types_json",
    } <= result_columns
    assert {"capability_snapshot_json", "gpu_label", "office_capability"} <= executor_columns
    assert {"kind", "target_keys_json", "conflict_id"} <= operation_columns
    assert conflict_tables == {"sync_conflicts"}


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


def test_cloud_identity_devices_and_service_accounts_enforce_scope(tmp_path: Path) -> None:
    app = create_cloud_app(tmp_path / "control.db", tmp_path / "objects")
    alice = {"X-Actor-ID": "alice"}
    bob = {"X-Actor-ID": "bob"}
    mallory = {"X-Actor-ID": "mallory"}
    with TestClient(app) as client:
        organization = client.post(
            "/v1/organizations", json={"name": "Studio"}, headers=alice
        )
        assert organization.status_code == 201
        organization_id = organization.json()["organization_id"]
        workspace = client.post(
            "/v1/workspaces",
            json={"name": "Team", "organization_id": organization_id},
            headers=alice,
        )
        assert workspace.status_code == 201
        workspace_id = workspace.json()["workspace_id"]
        assert workspace.json()["organization_id"] == organization_id
        assert client.get("/v1/organizations", headers=alice).json()["items"] == [
            organization.json()
        ]
        assert (
            client.post(
                "/v1/workspaces",
                json={"name": "Stolen", "organization_id": organization_id},
                headers=mallory,
            ).status_code
            == 404
        )

        first_member = client.post(
            f"/v1/workspaces/{workspace_id}/members",
            json={"actor_id": "bob", "role": "viewer"},
            headers=alice,
        )
        second_member = client.post(
            f"/v1/workspaces/{workspace_id}/members",
            json={"actor_id": "bob", "role": "reviewer"},
            headers=alice,
        )
        assert first_member.json()["membership_version"] == 1
        assert second_member.json()["membership_version"] == 2
        assert re.fullmatch(r"[0-9a-f-]{36}", second_member.json()["user_id"])

        device_id = str(uuid4())
        device = client.post(
            "/v1/devices",
            json={"device_id": device_id, "name": "Laptop", "platform": "windows"},
            headers=alice,
        )
        assert device.status_code == 201
        assert device.json()["status"] == "active"
        assert (
            client.post(
                "/v1/devices",
                json={"device_id": device_id, "name": "Other", "platform": "linux"},
                headers=mallory,
            ).status_code
            == 409
        )
        assert client.delete(f"/v1/devices/{device_id}", headers=mallory).status_code == 404
        revoked = client.delete(f"/v1/devices/{device_id}", headers=alice)
        assert revoked.json()["status"] == "revoked"
        assert client.get("/v1/me", headers=alice).json()["devices"] == [revoked.json()]

        account = client.post(
            f"/v1/workspaces/{workspace_id}/service-accounts",
            json={"name": "renderer"},
            headers=alice,
        )
        assert account.status_code == 201
        account_id = account.json()["service_account_id"]
        assert (
            client.get(
                f"/v1/workspaces/{workspace_id}/service-accounts", headers=bob
            ).status_code
            == 403
        )
        assert (
            client.get(
                f"/v1/workspaces/{workspace_id}/service-accounts", headers=mallory
            ).status_code
            == 404
        )
        disabled = client.delete(
            f"/v1/workspaces/{workspace_id}/service-accounts/{account_id}", headers=alice
        )
        assert disabled.json()["status"] == "disabled"


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
        content = b"asset"
        object_id = "sha256:" + hashlib.sha256(content).hexdigest()
        upload = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/objects/uploads",
            json={
                "object": {
                    "object_id": object_id,
                    "size_bytes": 5,
                    "media_type": "application/octet-stream",
                    "classification": "internal",
                }
            },
            headers=headers,
        )
        assert upload.status_code == 201
        part = client.put(
            upload.json()["parts"][0]["local_endpoint"],
            content=content,
            headers=headers,
        )
        assert part.status_code == 200
        invalid_complete = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/objects/uploads/{upload.json()['upload_id']}/complete",
            json={"parts": [{"part_number": 1, "etag": "etag", "size_bytes": 4}]},
            headers=headers,
        )
        assert invalid_complete.status_code == 422
        assert invalid_complete.json()["detail"] == "upload_size_mismatch"
        completed = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/objects/uploads/{upload.json()['upload_id']}/complete",
            json={
                "parts": [
                    {
                        "part_number": 1,
                        "etag": part.json()["etag"],
                        "size_bytes": len(content),
                    }
                ]
            },
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
        downloaded = client.get(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/objects/{object_id}/content",
            headers=headers,
        )
        assert downloaded.status_code == 200
        assert downloaded.content == content
        comment = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/comments",
            json={
                "body": "Review",
                "anchor": {
                    "revision_id": revision_id,
                    "time_ms": 100,
                    "end_time_ms": 200,
                    "evidence_object_id": object_id,
                },
            },
            headers=headers,
        )
        assert comment.status_code == 201
        assert comment.json()["anchor"]["evidence_object_id"] == object_id
        review = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/reviews",
            json={
                "revision_id": revision_id,
                "content_sha256": project["head"]["content_sha256"],
                "decision": "approved",
            },
            headers=headers,
        )
        assert review.status_code == 201
        lease = client.put(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/lease",
            json={
                "client_id": str(uuid4()),
                "base_revision_id": revision_id,
                "scope": "project_edit",
                "requested_ttl_seconds": 60,
            },
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
            json=_remote_job_request(revision_id),
            headers=_idempotent(headers),
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


def test_cloud_reviews_expire_and_force_lease_release_is_audited(tmp_path: Path) -> None:
    app = create_cloud_app(tmp_path / "control.db", tmp_path / "objects")
    alice = {"X-Actor-ID": "alice"}
    bob = {"X-Actor-ID": "bob"}
    with TestClient(app) as client:
        workspace_id = client.post(
            "/v1/workspaces", json={"name": "Team"}, headers=alice
        ).json()["workspace_id"]
        project = client.post(
            f"/v1/workspaces/{workspace_id}/projects",
            json={"name": "Course", "manifest": {"pages": []}},
            headers=alice,
        ).json()
        project_id = project["project_id"]
        revision_id = project["current_revision_id"]
        client.post(
            f"/v1/workspaces/{workspace_id}/members",
            json={"actor_id": "bob", "role": "editor"},
            headers=alice,
        )
        review = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/reviews",
            json={
                "revision_id": revision_id,
                "content_sha256": project["head"]["content_sha256"],
                "decision": "approved",
            },
            headers=alice,
        )
        assert review.json()["status"] == "current"
        lease = client.put(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/lease",
            json={
                "client_id": str(uuid4()),
                "base_revision_id": revision_id,
                "scope": "timeline_edit",
                "requested_ttl_seconds": 60,
            },
            headers=bob,
        )
        assert lease.status_code == 200
        assert (
            client.delete(
                f"/v1/workspaces/{workspace_id}/projects/{project_id}/lease", headers=alice
            ).status_code
            == 422
        )
        released = client.delete(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/lease",
            params={"reason": "stale editor session"},
            headers=alice,
        )
        assert released.status_code == 200
        assert released.json()["action"] == "force_released"
        with sqlite3.connect(tmp_path / "control.db") as db:
            audit = db.execute(
                "SELECT action, reason FROM lease_audit_events WHERE id=?",
                (released.json()["audit_event_id"],),
            ).fetchone()
        assert audit == ("force_released", "stale editor session")

        operation = _operation(workspace_id, project_id, revision_id)
        assert (
            client.post(
                f"/v1/workspaces/{workspace_id}/projects/{project_id}/operations",
                json=operation,
                headers=alice,
            ).status_code
            == 201
        )
        reviews = client.get(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/reviews", headers=alice
        ).json()["items"]
        assert reviews[0]["status"] == "expired"


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
            json=_remote_job_request(
                project["current_revision_id"],
                fingerprints={
                    "provider_policy": "sha256:" + "1" * 64,
                    "platform": "sha256:" + "2" * 64,
                    "runtime": "sha256:" + "3" * 64,
                    "input": "sha256:" + "4" * 64,
                },
            ),
            headers=_idempotent(headers),
        ).json()
        fingerprints = job["fingerprints"]
        result = {"media_type": "video/mp4", "duration_ms": 1000}
        output_content = b"output"
        output_object = "sha256:" + hashlib.sha256(output_content).hexdigest()
        result_url = (
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}"
            f"/jobs/{job['job_id']}/result"
        )
        unowned = client.post(
            result_url,
            json={
                "attempt_id": job["attempt_id"],
                "executor_id": executor["executor_id"],
                "status": "completed",
                "result_schema_version": 1,
                "result": result,
                "result_sha256": canonical_sha256(result),
                "output_refs": ["artifact://" + output_object],
                "output_media_types": {
                    "artifact://" + output_object: "application/octet-stream"
                },
                "fingerprints": fingerprints,
            },
            headers={**headers, "X-Attempt-Token": job["attempt_access_token"]},
        )
        assert unowned.status_code == 422
        assert unowned.json()["detail"] == "result_object_not_owned"
        upload = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}/objects/uploads",
            json={
                "object": {
                    "object_id": output_object,
                    "size_bytes": len(output_content),
                    "media_type": "application/octet-stream",
                    "classification": "internal",
                }
            },
            headers=headers,
        )
        assert upload.status_code == 201
        output_part = client.put(
            upload.json()["parts"][0]["local_endpoint"],
            content=output_content,
            headers=headers,
        )
        assert output_part.status_code == 200
        assert client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}"
            f"/objects/uploads/{upload.json()['upload_id']}/complete",
            json={"parts": [{"part_number": 1, "etag": output_part.json()["etag"]}]},
            headers=headers,
        ).status_code == 201
        report = {
            "attempt_id": job["attempt_id"],
            "executor_id": executor["executor_id"],
            "status": "completed",
            "result_schema_version": 1,
            "result": result,
            "result_sha256": canonical_sha256(result),
            "output_refs": ["artifact://" + output_object],
            "output_media_types": {
                "artifact://" + output_object: "application/octet-stream"
            },
            "fingerprints": fingerprints,
        }
        attempt_headers = {**headers, "X-Attempt-Token": job["attempt_access_token"]}
        completed = client.post(result_url, json=report, headers=attempt_headers)
        assert completed.status_code == 200
        assert completed.json()["status"] == "completed"
        repeated = client.post(result_url, json=report, headers=attempt_headers)
        assert repeated.status_code == 200
        job_after = client.get(
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}/jobs/{job['job_id']}",
            headers=headers,
        ).json()
        assert job_after["result"]["result_sha256"] == report["result_sha256"]
        assert job_after["result"]["output_refs"] == report["output_refs"]
        assert job_after["result"]["fingerprints"] == fingerprints

        mismatch = dict(report)
        mismatch["fingerprints"] = {**fingerprints, "runtime": "sha256:" + "9" * 64}
        rejected = client.post(result_url, json=mismatch, headers=attempt_headers)
        assert rejected.status_code == 422
        assert rejected.json()["detail"] == "job_fingerprint_mismatch"

        conflict = dict(report)
        conflict_result = {**result, "duration_ms": 2000}
        conflict["result"] = conflict_result
        conflict["result_sha256"] = canonical_sha256(conflict_result)
        rejected_conflict = client.post(result_url, json=conflict, headers=attempt_headers)
        assert rejected_conflict.status_code == 409
        assert rejected_conflict.json()["detail"] == "attempt_result_conflict"


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
            json=_remote_job_request(
                project["current_revision_id"],
                required_capabilities=["gpu.nvidia"],
            ),
            headers=_idempotent(headers),
        ).json()
    assert job["status"] == "dispatched"
    assert job["executor_id"] == capable["executor_id"]


def test_remote_job_provider_budget_is_checked_at_queue_and_claim(tmp_path: Path) -> None:
    db_path = tmp_path / "control.db"
    app = create_cloud_app(db_path, tmp_path / "objects")
    headers = {"X-Actor-ID": "alice"}
    budget = {
        "schema_version": 1,
        "timeout_ms": 120_000,
        "max_attempts": 2,
        "max_input_bytes": 1_073_741_824,
        "max_output_bytes": 4_294_967_296,
        "max_cost_minor": 100,
    }
    with TestClient(app) as client:
        workspace_id = client.post(
            "/v1/workspaces", json={"name": "Team"}, headers=headers
        ).json()["workspace_id"]
        project = client.post(
            f"/v1/workspaces/{workspace_id}/projects",
            json={"name": "Course"},
            headers=headers,
        ).json()
        job_url = f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}/jobs"

        over_budget = client.post(
            job_url,
            json=_remote_job_request(
                project["current_revision_id"],
                provider_budget=budget,
                provider_cost_estimate_minor=101,
            ),
            headers=_idempotent(headers),
        )
        assert over_budget.status_code == 422

        queued = client.post(
            job_url,
            json=_remote_job_request(
                project["current_revision_id"],
                provider_budget=budget,
                provider_cost_estimate_minor=50,
                required_region="local",
            ),
            headers=_idempotent(headers),
        )
        assert queued.status_code == 202
        job = queued.json()
        assert job["status"] == "queued"
        assert job["provider_budget"]["max_cost_minor"] == 100
        assert job["provider_cost_estimate_minor"] == 50

        executor = client.post(
            f"/v1/workspaces/{workspace_id}/executors",
            json={
                "platform": "linux",
                "capabilities": ["render"],
                "region": "local",
                "ttl_seconds": 900,
            },
            headers=headers,
        ).json()
        with sqlite3.connect(db_path) as db:
            db.execute(
                "UPDATE jobs SET provider_cost_estimate_minor=101 WHERE id=?",
                (job["job_id"],),
            )
        claim_url = f"{job_url}/{job['job_id']}/claim"
        rejected = client.post(
            claim_url,
            json={"executor_id": executor["executor_id"]},
            headers=_idempotent(headers),
        )
        assert rejected.status_code == 409
        assert rejected.json()["detail"] == "provider_budget_exceeded"

        with sqlite3.connect(db_path) as db:
            db.execute(
                "UPDATE jobs SET provider_cost_estimate_minor=50 WHERE id=?",
                (job["job_id"],),
            )
        accepted = client.post(
            claim_url,
            json={"executor_id": executor["executor_id"]},
            headers=_idempotent(headers),
        )
        assert accepted.status_code == 200
        attempt = accepted.json()
        attempt_input = client.get(
            f"{job_url}/{job['job_id']}/attempts/{attempt['attempt_id']}/input",
            headers={**headers, "X-Attempt-Token": attempt["attempt_access_token"]},
        )
        assert attempt_input.status_code == 200
        assert attempt_input.json()["provider_budget"]["max_cost_minor"] == 100
        assert attempt_input.json()["provider_cost_estimate_minor"] == 50


def test_remote_job_idempotency_region_and_attempt_lease_reclaim(tmp_path: Path) -> None:
    db_path = tmp_path / "control.db"
    app = create_cloud_app(db_path, tmp_path / "objects")
    headers = {"X-Actor-ID": "alice"}
    east_id = "00000000-0000-0000-0000-000000000001"
    west_one_id = "00000000-0000-0000-0000-000000000002"
    west_two_id = "00000000-0000-0000-0000-000000000003"
    with TestClient(app) as client:
        workspace_id = client.post(
            "/v1/workspaces", json={"name": "Team"}, headers=headers
        ).json()["workspace_id"]
        project = client.post(
            f"/v1/workspaces/{workspace_id}/projects",
            json={"name": "Course"},
            headers=headers,
        ).json()
        for executor_id, region in ((east_id, "east"), (west_one_id, "west")):
            registered = client.post(
                f"/v1/workspaces/{workspace_id}/executors",
                json={
                    "executor_id": executor_id,
                    "platform": "windows",
                    "capabilities": ["render", "gpu.nvidia", "office.powerpoint"],
                    "region": region,
                    "gpu_label": "nvidia",
                    "office_capability": "microsoft_office",
                    "ttl_seconds": 900,
                },
                headers=headers,
            )
            assert registered.status_code == 201

        create_headers = _idempotent(headers)
        request = _remote_job_request(
            project["current_revision_id"],
            required_capabilities=["gpu.nvidia", "office.powerpoint"],
            required_region="west",
            parameters={"input_objects": ["sha256:" + "a" * 64]},
        )
        created = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}/jobs",
            json=request,
            headers=create_headers,
        )
        assert created.status_code == 202
        job = created.json()
        assert job["executor_id"] == west_one_id
        assert job["attempt_count"] == 1
        assert job["attempt_id"]
        assert job["lease_id"]
        assert job["attempt_access_token"]
        with sqlite3.connect(db_path) as db:
            token_hash = db.execute(
                "SELECT attempt_token_hash FROM jobs WHERE id=?", (job["job_id"],)
            ).fetchone()[0]
        assert token_hash.startswith("sha256:")
        assert token_hash != job["attempt_access_token"]

        renewed = client.post(
            f"/v1/workspaces/{workspace_id}/executors",
            json={
                "executor_id": west_one_id,
                "platform": "windows",
                "capabilities": ["render", "gpu.nvidia", "office.powerpoint"],
                "region": "west",
                "gpu_label": "nvidia",
                "office_capability": "microsoft_office",
                "ttl_seconds": 900,
            },
            headers=headers,
        )
        assert renewed.status_code == 201

        duplicate = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}/jobs",
            json=request,
            headers=create_headers,
        )
        assert duplicate.status_code == 202
        assert duplicate.json()["job_id"] == job["job_id"]
        assert duplicate.json()["attempt_count"] == 1
        assert "attempt_access_token" not in duplicate.json()

        changed_request = {**request, "kind": "export"}
        conflict = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}/jobs",
            json=changed_request,
            headers=create_headers,
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"] == "job_idempotency_conflict"

        input_url = (
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}"
            f"/jobs/{job['job_id']}/attempts/{job['attempt_id']}/input"
        )
        assert client.get(input_url, headers=headers).status_code == 401
        assert (
            client.get(input_url, headers={**headers, "X-Attempt-Token": "x" * 43}).json()[
                "detail"
            ]
            == "attempt_token_invalid"
        )
        immutable_input = client.get(
            input_url,
            headers={**headers, "X-Attempt-Token": job["attempt_access_token"]},
        )
        assert immutable_input.status_code == 200
        assert immutable_input.json()["revision_id"] == project["current_revision_id"]
        assert immutable_input.json()["provider_policy_sha256"] == _PROVIDER_POLICY_SHA256

        active_claim = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}"
            f"/jobs/{job['job_id']}/claim",
            json={"executor_id": west_one_id, "requested_ttl_seconds": 120},
            headers=_idempotent(headers),
        )
        assert active_claim.status_code == 409
        assert active_claim.json()["detail"] == "job_attempt_lease_active"

        with sqlite3.connect(db_path) as db:
            db.execute(
                "UPDATE jobs SET lease_expires_at=?, attempt_token_expires_at=? WHERE id=?",
                ("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", job["job_id"]),
            )
            db.execute(
                "UPDATE executors SET status='offline', expires_at=? WHERE id=?",
                ("2026-01-01T00:00:00Z", west_one_id),
            )

        replacement = client.post(
            f"/v1/workspaces/{workspace_id}/executors",
            json={
                "executor_id": west_two_id,
                "platform": "linux",
                "capabilities": ["render", "gpu.nvidia", "office.powerpoint"],
                "region": "west",
                "gpu_label": "nvidia",
                "office_capability": "libreoffice",
                "ttl_seconds": 900,
            },
            headers=headers,
        )
        assert replacement.status_code == 201
        reclaimed = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}"
            f"/jobs/{job['job_id']}/claim",
            json={"executor_id": west_two_id, "requested_ttl_seconds": 120},
            headers=_idempotent(headers),
        )
        assert reclaimed.status_code == 200
        second = reclaimed.json()
        assert second["executor_id"] == west_two_id
        assert second["attempt_count"] == 2
        assert second["attempt_id"] != job["attempt_id"]
        assert second["lease_id"] != job["lease_id"]
        with sqlite3.connect(db_path) as db:
            attempt_events = db.execute(
                "SELECT attempt_id FROM job_attempt_events WHERE job_id=? ORDER BY occurred_at",
                (job["job_id"],),
            ).fetchall()
        assert {row[0] for row in attempt_events} == {job["attempt_id"], second["attempt_id"]}

        stale_result = {"message": "stale"}
        rejected_stale = client.post(
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}"
            f"/jobs/{job['job_id']}/result",
            json={
                "attempt_id": job["attempt_id"],
                "executor_id": west_one_id,
                "status": "completed",
                "result_schema_version": 1,
                "result": stale_result,
                "result_sha256": canonical_sha256(stale_result),
                "output_refs": [],
                "output_media_types": {},
                "fingerprints": job["fingerprints"],
            },
            headers={**_idempotent(headers), "X-Attempt-Token": job["attempt_access_token"]},
        )
        assert rejected_stale.status_code == 409
        assert rejected_stale.json()["detail"] == "job_attempt_mismatch"

        second_input_url = (
            f"/v1/workspaces/{workspace_id}/projects/{project['project_id']}"
            f"/jobs/{job['job_id']}/attempts/{second['attempt_id']}/input"
        )
        assert (
            client.get(
                second_input_url,
                headers={**headers, "X-Attempt-Token": second["attempt_access_token"]},
            ).status_code
            == 200
        )
