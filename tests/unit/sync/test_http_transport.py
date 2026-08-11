from __future__ import annotations

import httpx
import pytest
from workbench.sync import HttpSyncTransport, SyncTransportError


def test_http_transport_posts_scoped_operations_without_persisting_token() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"operation_id": "op-1", "cursor": "cursor-1"})

    transport = HttpSyncTransport(
        "https://cloud.example.test",
        workspace_id="workspace-1",
        project_id="project-1",
        actor_id="actor-1",
        token_provider=lambda: "secret-token",
        transport=httpx.MockTransport(handler),
    )
    result = transport.append_operation("op-1", {"kind": "page.insert"})
    transport.close()

    assert result == {"status": "accepted", "cursor": "cursor-1"}
    assert requests[0].url.path.endswith("/v1/workspaces/workspace-1/projects/project-1/operations")
    assert requests[0].headers["Authorization"] == "Bearer secret-token"
    assert "secret-token" not in requests[0].content.decode()


def test_http_transport_maps_conflicts_and_requires_storage_gateway() -> None:
    transport = HttpSyncTransport(
        "https://cloud.example.test",
        workspace_id="workspace-1",
        project_id="project-1",
        actor_id="actor-1",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(409, json={"detail": {"head_revision_id": "rev-2"}})
        ),
    )
    with pytest.raises(SyncTransportError) as raised:
        transport.append_operation("op-1", {"kind": "page.insert"})
    assert raised.value.conflict_id == "rev-2"
    with pytest.raises(SyncTransportError, match="storage gateway"):
        transport.download_object("sha256:" + "a" * 64)
    transport.close()


def test_http_transport_lists_operations_with_resume_cursor() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"items": [{"operation_id": "op-2"}]})

    transport = HttpSyncTransport(
        "https://cloud.example.test",
        workspace_id="workspace-1",
        project_id="project-1",
        actor_id="actor-1",
        transport=httpx.MockTransport(handler),
    )
    assert transport.list_operations("op-1") == {"items": [{"operation_id": "op-2"}]}
    assert requests[0].url.params["cursor"] == "op-1"
    transport.close()
