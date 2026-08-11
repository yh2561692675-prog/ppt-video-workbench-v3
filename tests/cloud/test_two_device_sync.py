from __future__ import annotations

from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from workbench.contracts.p2_platform import canonical_sha256
from workbench.sync import HttpSyncTransport, SyncClient

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


def _transport(
    api: TestClient,
    *,
    workspace_id: str,
    project_id: str,
    actor_id: str,
) -> HttpSyncTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.query:
            path += "?" + request.url.query.decode()
        forward = {
            key: request.headers[key]
            for key in ("x-actor-id", "authorization")
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
