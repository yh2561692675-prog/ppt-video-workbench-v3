from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from workbench_peripheral_adapter.client import (
    DisabledPeripheralClient,
    HttpPeripheralClient,
    PeripheralRequestRejected,
    PeripheralUnavailable,
)
from workbench_peripheral_adapter.dto import SubmitJobDto


def _submit_dto() -> SubmitJobDto:
    return SubmitJobDto(
        schema_version="1.0",
        job_id=uuid4(),
        project_id=uuid4(),
        job_type="system.echo",
        requested_by="workbench",
        priority=50,
        idempotency_key=uuid4().hex,
        inputs=(),
        parameters={"text": "adapter test"},
        created_at=datetime.now(UTC),
    )


def test_disabled_client_reports_unavailable_without_network() -> None:
    client = DisabledPeripheralClient()

    with pytest.raises(PeripheralUnavailable, match="disabled"):
        client.get_job_status(uuid4())


@pytest.mark.parametrize(
    "base_url",
    [
        "http://0.0.0.0:8765",
        "http://example.com:8765",
        "https://127.0.0.1:8765",
        "http://" + "user:secret@" + "127.0.0.1:8765",
        "http://127.0.0.1:8765/internal",
    ],
)
def test_http_client_rejects_non_loopback_or_credentialed_origin(base_url: str) -> None:
    with pytest.raises(ValueError, match="loopback HTTP origin"):
        HttpPeripheralClient(base_url)


def test_timeout_maps_to_user_safe_unavailable() -> None:
    def timeout(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    client = HttpPeripheralClient(
        "http://127.0.0.1:8765",
        timeout_seconds=0.1,
        transport=httpx.MockTransport(timeout),
    )

    with pytest.raises(PeripheralUnavailable) as error:
        client.get_job_status(uuid4())

    assert error.value.user_message == "外围功能暂不可用，原有视频流程仍可继续使用。"


def test_422_preserves_stable_error_code_and_user_message() -> None:
    def reject(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            422,
            request=request,
            json={
                "error": {
                    "code": "INVALID_INPUT",
                    "message": "请求内容无效，请检查后重试。",
                    "retryable": False,
                    "correlation_id": str(uuid4()),
                }
            },
        )

    client = HttpPeripheralClient(
        "http://127.0.0.1:8765",
        transport=httpx.MockTransport(reject),
    )

    with pytest.raises(PeripheralRequestRejected) as error:
        client.submit_job(_submit_dto())

    assert error.value.status_code == 422
    assert error.value.code == "INVALID_INPUT"
    assert error.value.user_message == "请求内容无效，请检查后重试。"


def test_artifact_dto_does_not_expose_internal_relative_path() -> None:
    job_id = uuid4()
    artifact_id = uuid4()
    project_id = uuid4()

    def artifacts(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json=[
                {
                    "artifact_id": str(artifact_id),
                    "job_id": str(job_id),
                    "project_id": str(project_id),
                    "logical_name": "echo-text",
                    "kind": "text",
                    "relative_path": "projects/private/artifacts/echo.txt",
                    "version": 1,
                    "size_bytes": 5,
                    "sha256": "0" * 64,
                    "verified_at": datetime.now(UTC).isoformat(),
                    "is_current": True,
                }
            ],
        )

    client = HttpPeripheralClient(
        "http://127.0.0.1:8765",
        transport=httpx.MockTransport(artifacts),
    )

    result = client.list_artifacts(job_id)

    assert result[0].artifact_id == artifact_id
    assert "path" not in result[0].model_dump()
    assert "relative_path" not in result[0].model_dump()


def test_artifact_stream_yields_content_without_exposing_path() -> None:
    job_id = uuid4()
    artifact_id = uuid4()
    payload = b"streamed payload"

    def content(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            headers={
                "Content-Length": str(len(payload)),
                "Digest": f"sha-256={'a' * 64}",
            },
            content=payload,
        )

    client = HttpPeripheralClient(
        "http://127.0.0.1:8765",
        transport=httpx.MockTransport(content),
    )

    assert b"".join(client.stream_artifact(job_id, artifact_id)) == payload
