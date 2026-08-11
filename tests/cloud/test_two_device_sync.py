from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from workbench.contracts.p2_platform import canonical_sha256
from workbench.sync import HttpSyncTransport, SyncClient, SyncTransportError

from cloud_prototype.app import create_cloud_app


def _operation(
    workspace_id: str, project_id: str, revision_id: str, *, title: str
) -> dict[str, object]:
    payload = {"title": title}
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


def _object_operation(
    workspace_id: str,
    project_id: str,
    revision_id: str,
    *,
    clip_id: str,
    value: str,
    client_id: str,
    sequence: int,
) -> dict[str, object]:
    payload = {"clip_id": clip_id, "patch": {"text": value}}
    return {
        "schema_version": 1,
        "operation_id": str(uuid4()),
        "idempotency_key": str(uuid4()),
        "attempt_id": str(uuid4()),
        "workspace_id": workspace_id,
        "project_id": project_id,
        "base_revision_id": revision_id,
        "client_id": client_id,
        "client_sequence": sequence,
        "kind": "timeline.patch",
        "payload": payload,
        "payload_sha256": canonical_sha256(payload),
        "created_at": "2026-08-11T00:00:00Z",
    }


def _typed_operation(
    workspace_id: str,
    project_id: str,
    revision_id: str,
    *,
    kind: str,
    payload: dict[str, object],
    client_id: str,
    sequence: int,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "operation_id": str(uuid4()),
        "idempotency_key": str(uuid4()),
        "attempt_id": str(uuid4()),
        "workspace_id": workspace_id,
        "project_id": project_id,
        "base_revision_id": revision_id,
        "client_id": client_id,
        "client_sequence": sequence,
        "kind": kind,
        "payload": payload,
        "payload_sha256": canonical_sha256(payload),
        "created_at": "2026-08-11T00:00:00Z",
    }


def _transport(
    api: TestClient,
    *,
    workspace_id: str,
    project_id: str,
    actor_id: str,
    device_id: str | None = None,
) -> HttpSyncTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.query:
            path += "?" + request.url.query.decode()
        forward = {
            key: request.headers[key]
            for key in (
                "x-actor-id",
                "x-device-id",
                "authorization",
                "content-type",
                "idempotency-key",
            )
            if key in request.headers
        }
        response = api.request(request.method, path, headers=forward, content=request.content)
        return httpx.Response(
            response.status_code,
            headers=dict(response.headers),
            content=response.content,
            request=request,
        )

    return HttpSyncTransport(
        "https://cloud.example.test",
        workspace_id=workspace_id,
        project_id=project_id,
        actor_id=actor_id,
        device_id=device_id,
        transport=httpx.MockTransport(handler),
    )


def test_two_device_http_sync_pull_and_stale_conflict(tmp_path) -> None:
    app = create_cloud_app(tmp_path / "control.db", tmp_path / "objects")
    with TestClient(app) as api:
        alice = {"X-Actor-ID": "alice"}
        workspace = api.post("/v1/workspaces", json={"name": "Team"}, headers=alice).json()
        workspace_id = workspace["workspace_id"]
        project = api.post(
            f"/v1/workspaces/{workspace_id}/projects",
            json={"name": "Course", "manifest": {"pages": []}},
            headers=alice,
        ).json()
        project_id = project["project_id"]
        initial_revision = project["current_revision_id"]
        assert (
            api.post(
                f"/v1/workspaces/{workspace_id}/members",
                json={"actor_id": "bob", "role": "editor"},
                headers=alice,
            ).status_code
            == 201
        )

        device_a = SyncClient(tmp_path / "device-a" / "sync.db", enabled=True)
        device_b = SyncClient(tmp_path / "device-b" / "sync.db", enabled=True)
        transport_a = _transport(
            api, workspace_id=workspace_id, project_id=project_id, actor_id="alice"
        )
        transport_b = _transport(
            api, workspace_id=workspace_id, project_id=project_id, actor_id="bob"
        )
        try:
            operation = _operation(workspace_id, project_id, initial_revision, title="from-a")
            assert device_a.enqueue(operation["operation_id"], operation)
            assert device_a.flush(transport_a).accepted == 1

            pulled = device_b.pull(transport_b)
            assert len(pulled) == 1
            assert pulled[0]["payload"]["title"] == "from-a"
            pending = device_b.pending_remote_operations()
            assert pending[0]["operation_id"] == pulled[0]["operation_id"]
            device_b.mark_remote_applied(str(pulled[0]["operation_id"]))
            assert device_b.pending_remote_operations() == []

            stale = _operation(workspace_id, project_id, initial_revision, title="from-b")
            assert device_b.enqueue(stale["operation_id"], stale)
            result = device_b.flush(transport_b)
            assert result.conflict == 1
            assert device_b.state().conflict == 1
        finally:
            transport_a.close()
            transport_b.close()


def test_two_device_offline_merge_manual_resolution_and_revocation(tmp_path) -> None:
    app = create_cloud_app(tmp_path / "control.db", tmp_path / "objects")
    with TestClient(app) as api:
        alice_headers = {"X-Actor-ID": "alice"}
        bob_headers = {"X-Actor-ID": "bob"}
        organization = api.post(
            "/v1/organizations", json={"name": "Studio"}, headers=alice_headers
        ).json()
        workspace = api.post(
            "/v1/workspaces",
            json={"name": "Team", "organization_id": organization["organization_id"]},
            headers=alice_headers,
        ).json()
        workspace_id = workspace["workspace_id"]
        project = api.post(
            f"/v1/workspaces/{workspace_id}/projects",
            json={"name": "Course", "manifest": {"pages": []}},
            headers=alice_headers,
        ).json()
        project_id = project["project_id"]
        initial_revision = project["current_revision_id"]
        assert (
            api.post(
                f"/v1/workspaces/{workspace_id}/members",
                json={"actor_id": "bob", "role": "editor"},
                headers=alice_headers,
            ).status_code
            == 201
        )
        device_a_id, device_b_id = str(uuid4()), str(uuid4())
        assert (
            api.post(
                "/v1/devices",
                json={"device_id": device_a_id, "name": "A", "platform": "windows"},
                headers=alice_headers,
            ).status_code
            == 201
        )
        assert (
            api.post(
                "/v1/devices",
                json={"device_id": device_b_id, "name": "B", "platform": "linux"},
                headers=bob_headers,
            ).status_code
            == 201
        )

        client_a_id, client_b_id = str(uuid4()), str(uuid4())
        device_a = SyncClient(tmp_path / "device-a" / "sync.db", enabled=True)
        device_b = SyncClient(tmp_path / "device-b" / "sync.db", enabled=True)
        transport_a = _transport(
            api,
            workspace_id=workspace_id,
            project_id=project_id,
            actor_id="alice",
            device_id=device_a_id,
        )
        transport_b = _transport(
            api,
            workspace_id=workspace_id,
            project_id=project_id,
            actor_id="bob",
            device_id=device_b_id,
        )
        try:
            clip_a, clip_b = str(uuid4()), str(uuid4())
            edit_a = _object_operation(
                workspace_id,
                project_id,
                initial_revision,
                clip_id=clip_a,
                value="offline-a",
                client_id=client_a_id,
                sequence=1,
            )
            edit_b = _object_operation(
                workspace_id,
                project_id,
                initial_revision,
                clip_id=clip_b,
                value="offline-b",
                client_id=client_b_id,
                sequence=1,
            )
            assert device_a.enqueue(str(edit_a["operation_id"]), edit_a)
            assert device_b.enqueue(str(edit_b["operation_id"]), edit_b)
            assert device_a.flush(transport_a).accepted == 1
            assert device_b.flush(transport_b).accepted == 1

            merged_project = api.get(
                f"/v1/workspaces/{workspace_id}/projects/{project_id}",
                headers=alice_headers,
            ).json()
            merged_objects = merged_project["head"]["manifest"]["sync_objects"]
            assert {f"clip:{clip_a}", f"clip:{clip_b}"} <= set(merged_objects)

            shared_clip = str(uuid4())
            shared_base = merged_project["current_revision_id"]
            shared_a = _object_operation(
                workspace_id,
                project_id,
                shared_base,
                clip_id=shared_clip,
                value="alice-version",
                client_id=client_a_id,
                sequence=2,
            )
            shared_b = _object_operation(
                workspace_id,
                project_id,
                shared_base,
                clip_id=shared_clip,
                value="bob-version",
                client_id=client_b_id,
                sequence=2,
            )
            assert device_a.enqueue(str(shared_a["operation_id"]), shared_a)
            assert device_b.enqueue(str(shared_b["operation_id"]), shared_b)
            assert device_a.flush(transport_a).accepted == 1
            conflict_result = device_b.flush(transport_b)
            assert conflict_result.conflict == 1
            local_conflict = device_b.conflicts(status="open")[0]
            assert local_conflict["details"]["kind"] == "same_field"
            assert local_conflict["details"]["paths"] == [f"clip:{shared_clip}"]

            current = api.get(
                f"/v1/workspaces/{workspace_id}/projects/{project_id}",
                headers=alice_headers,
            ).json()
            resolved = device_b.resolve_conflict(
                transport_b,
                str(shared_b["operation_id"]),
                strategy="merged",
                expected_head_revision_id=current["current_revision_id"],
                reason="reviewed by both editors",
                merged_payload={
                    "clip_id": shared_clip,
                    "patch": {"text": "merged-version"},
                },
            )
            assert resolved["status"] == "resolved"
            assert device_b.conflicts(status="open") == []
            final_project = api.get(
                f"/v1/workspaces/{workspace_id}/projects/{project_id}",
                headers=alice_headers,
            ).json()
            assert final_project["head"]["manifest"]["sync_objects"][f"clip:{shared_clip}"][
                "payload"
            ]["patch"]["text"] == "merged-version"

            head_revision = final_project["current_revision_id"]
            head_hash = final_project["head"]["content_sha256"]
            assert (
                api.post(
                    f"/v1/workspaces/{workspace_id}/projects/{project_id}/comments",
                    json={
                        "body": "please review",
                        "anchor": {"revision_id": head_revision, "clip_id": shared_clip},
                    },
                    headers=bob_headers,
                ).status_code
                == 201
            )
            assert (
                api.post(
                    f"/v1/workspaces/{workspace_id}/projects/{project_id}/reviews",
                    json={
                        "revision_id": head_revision,
                        "content_sha256": head_hash,
                        "decision": "approved",
                    },
                    headers=alice_headers,
                ).status_code
                == 201
            )
            lease = api.put(
                f"/v1/workspaces/{workspace_id}/projects/{project_id}/lease",
                json={
                    "client_id": client_b_id,
                    "base_revision_id": head_revision,
                    "scope": "timeline_edit",
                    "requested_ttl_seconds": 60,
                },
                headers=bob_headers,
            )
            assert lease.status_code == 200
            assert (
                api.delete(
                    f"/v1/workspaces/{workspace_id}/projects/{project_id}/lease",
                    headers=bob_headers,
                ).status_code
                == 200
            )

            assert api.delete(f"/v1/devices/{device_b_id}", headers=bob_headers).status_code == 200
            with pytest.raises(SyncTransportError, match="operation pull rejected"):
                device_b.pull(transport_b)
            revoked_member = api.delete(
                f"/v1/workspaces/{workspace_id}/members/bob",
                headers={**alice_headers, "Idempotency-Key": str(uuid4())},
            )
            assert revoked_member.status_code == 200
            assert revoked_member.json()["status"] == "revoked"
            assert (
                api.get(f"/v1/workspaces/{workspace_id}/projects/{project_id}", headers=bob_headers)
                .status_code
                == 404
            )
        finally:
            transport_a.close()
            transport_b.close()


def test_delete_move_races_are_persisted_across_restart_and_tenant_scoped(
    tmp_path,
) -> None:
    database = tmp_path / "control.db"
    objects = tmp_path / "objects"
    alice = {"X-Actor-ID": "alice"}
    client_a, client_b = str(uuid4()), str(uuid4())

    app = create_cloud_app(database, objects)
    with TestClient(app) as api:
        workspace = api.post("/v1/workspaces", json={"name": "Primary"}, headers=alice).json()
        workspace_id = workspace["workspace_id"]
        project = api.post(
            f"/v1/workspaces/{workspace_id}/projects",
            json={"name": "Course", "manifest": {"pages": []}},
            headers=alice,
        ).json()
        project_id = project["project_id"]
        initial_revision = project["current_revision_id"]

        page_id = str(uuid4())
        remove = _typed_operation(
            workspace_id,
            project_id,
            initial_revision,
            kind="page.remove",
            payload={"page_id": page_id},
            client_id=client_a,
            sequence=1,
        )
        replace = _typed_operation(
            workspace_id,
            project_id,
            initial_revision,
            kind="page.replace",
            payload={"page_id": page_id, "title": "offline replacement"},
            client_id=client_b,
            sequence=1,
        )
        remove_result = api.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/operations",
            json=remove,
            headers=alice,
        )
        assert remove_result.status_code == 201
        delete_race = api.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/operations",
            json=replace,
            headers=alice,
        )
        assert delete_race.status_code == 409
        delete_conflict = delete_race.json()["detail"]
        assert delete_conflict["kind"] == "delete_modify"
        assert delete_conflict["paths"] == [f"page:{page_id}"]
        delete_resolution = api.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/conflicts/"
            f"{delete_conflict['conflict_id']}/resolve",
            json={
                "expected_head_revision_id": remove_result.json()["revision"]["revision_id"],
                "strategy": "keep_remote",
                "reason": "deletion wins",
            },
            headers={**alice, "Idempotency-Key": str(uuid4())},
        )
        assert delete_resolution.status_code == 200

        move_base = remove_result.json()["revision"]["revision_id"]
        first_move = _typed_operation(
            workspace_id,
            project_id,
            move_base,
            kind="page.move",
            payload={"page_id": str(uuid4()), "after_page_id": None},
            client_id=client_a,
            sequence=2,
        )
        second_move = _typed_operation(
            workspace_id,
            project_id,
            move_base,
            kind="page.move",
            payload={"page_id": str(uuid4()), "after_page_id": None},
            client_id=client_b,
            sequence=2,
        )
        first_move_result = api.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/operations",
            json=first_move,
            headers=alice,
        )
        assert first_move_result.status_code == 201
        move_race = api.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/operations",
            json=second_move,
            headers=alice,
        )
        assert move_race.status_code == 409
        move_conflict = move_race.json()["detail"]
        assert move_conflict["kind"] == "page_order"
        assert move_conflict["paths"] == ["page-order:root"]

        other_workspace = api.post(
            "/v1/workspaces", json={"name": "Other tenant"}, headers=alice
        ).json()
        other_project = api.post(
            f"/v1/workspaces/{other_workspace['workspace_id']}/projects",
            json={"name": "Other project", "manifest": {}},
            headers=alice,
        ).json()

    restarted_app = create_cloud_app(database, objects)
    with TestClient(restarted_app) as restarted:
        conflicts = restarted.get(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/conflicts",
            headers=alice,
        )
        assert conflicts.status_code == 200
        persisted = {item["conflict_id"]: item for item in conflicts.json()["items"]}
        assert persisted[delete_conflict["conflict_id"]]["status"] == "resolved"
        assert persisted[move_conflict["conflict_id"]]["status"] == "open"

        cross_tenant = restarted.post(
            f"/v1/workspaces/{other_workspace['workspace_id']}/projects/"
            f"{other_project['project_id']}/conflicts/{move_conflict['conflict_id']}/resolve",
            json={
                "expected_head_revision_id": other_project["current_revision_id"],
                "strategy": "keep_remote",
                "reason": "must not cross tenant boundary",
            },
            headers={**alice, "Idempotency-Key": str(uuid4())},
        )
        assert cross_tenant.status_code == 404

        resolved = restarted.post(
            f"/v1/workspaces/{workspace_id}/projects/{project_id}/conflicts/"
            f"{move_conflict['conflict_id']}/resolve",
            json={
                "expected_head_revision_id": first_move_result.json()["revision"][
                    "revision_id"
                ],
                "strategy": "keep_remote",
                "reason": "first page order wins",
            },
            headers={**alice, "Idempotency-Key": str(uuid4())},
        )
        assert resolved.status_code == 200
        assert resolved.json()["status"] == "resolved"
