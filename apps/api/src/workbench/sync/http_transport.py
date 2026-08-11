"""HTTP transport for the optional desktop outbox.

The transport is deliberately stateless: the bearer token is obtained for
each request and is never written to the outbox or included in operation
payloads. A storage gateway can be supplied for object bytes; the control
plane's authorization response alone is not treated as file content.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from .client import SyncTransportError


class HttpSyncTransport:
    def __init__(
        self,
        base_url: str,
        *,
        workspace_id: str,
        project_id: str,
        actor_id: str,
        token_provider: Callable[[], str | None] | None = None,
        object_downloader: Callable[[str], bytes] | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        parsed = httpx.URL(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.host:
            raise ValueError("sync base_url must be an absolute HTTP(S) URL")
        if not workspace_id or not project_id or not actor_id:
            raise ValueError("sync scope identifiers are required")
        self.base_url = str(parsed).rstrip("/")
        self.workspace_id = workspace_id
        self.project_id = project_id
        self.actor_id = actor_id
        self.token_provider = token_provider or (lambda: None)
        self.object_downloader = object_downloader
        self.client = httpx.Client(transport=transport, timeout=timeout_seconds)

    def append_operation(self, operation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = dict(payload)
        body.setdefault("operation_id", operation_id)
        response = self._request("POST", "/operations", json=body)
        if response.status_code == 409:
            detail = _json_detail(response)
            conflict_id = str(
                detail.get("head_revision_id") or detail.get("conflict_id") or "conflict"
            )
            raise SyncTransportError(
                "cloud revision conflict", retryable=False, conflict_id=conflict_id
            )
        if response.status_code == 429 or response.status_code >= 500:
            raise SyncTransportError("cloud sync temporarily unavailable", retryable=True)
        if not 200 <= response.status_code < 300:
            raise SyncTransportError("cloud sync operation rejected", retryable=False)
        result = _json_detail(response)
        return {
            "status": "accepted",
            "cursor": str(result.get("cursor") or result.get("operation_id") or operation_id),
        }

    def list_operations(self, cursor: str | None = None) -> dict[str, Any]:
        response = self._request(
            "GET", "/operations", params={"cursor": cursor} if cursor else None
        )
        if response.status_code == 429 or response.status_code >= 500:
            raise SyncTransportError("cloud sync temporarily unavailable", retryable=True)
        if not 200 <= response.status_code < 300:
            raise SyncTransportError("cloud sync operation pull rejected", retryable=False)
        result = _json_detail(response)
        return {"items": result.get("items", []) if isinstance(result, dict) else []}

    def download_object(self, object_id: str) -> bytes:
        if self.object_downloader is None:
            raise SyncTransportError(
                "cloud object storage gateway is not configured", retryable=False
            )
        try:
            return self.object_downloader(object_id)
        except (OSError, httpx.HTTPError) as error:
            raise SyncTransportError("cloud object download failed", retryable=True) from error

    def close(self) -> None:
        self.client.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}))
        headers["X-Actor-ID"] = self.actor_id
        token = self.token_provider()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            return self.client.request(
                method,
                f"{self.base_url}/v1/workspaces/{self.workspace_id}/projects/"
                f"{self.project_id}{path}",
                headers=headers,
                **kwargs,
            )
        except httpx.HTTPError as error:
            raise SyncTransportError("cloud sync network failure", retryable=True) from error


def _json_detail(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    if isinstance(payload, dict):
        detail = payload.get("detail")
        return detail if isinstance(detail, dict) else payload
    return {}
