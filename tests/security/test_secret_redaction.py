from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from workbench.integrations.llm.client import LlmClient, LlmIntegrationError
from workbench.main import create_app
from workbench.settings.secret_store import SecretProtector

TEST_KEY = "sk-" + "test-super-secret-123456"


class ReversibleTestProtector(SecretProtector):
    """Deterministic test double for the Windows DPAPI primitive only."""

    def protect(self, plaintext: bytes) -> bytes:
        return base64.b64encode(plaintext[::-1])

    def unprotect(self, ciphertext: bytes) -> bytes:
        return base64.b64decode(ciphertext)[::-1]


def _openai_transport(kind: str = "ok") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {TEST_KEY}"
        if kind == "unauthorized":
            return httpx.Response(401, json={"error": {"message": "invalid api key"}})
        if kind == "bad_model":
            return httpx.Response(404, json={"error": {"message": "model not found"}})
        if kind == "empty":
            return httpx.Response(200, json={"choices": []})
        if kind == "truncated":
            return httpx.Response(200, content=b'{"choices": [{"message":')
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "choices": [{"message": {"role": "assistant", "content": "连接成功"}}],
            },
        )

    return httpx.MockTransport(handler)


def test_profile_api_never_exposes_or_logs_plaintext_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    app = create_app(
        tmp_path,
        secret_protector=ReversibleTestProtector(),
        llm_transport=_openai_transport(),
    )

    with TestClient(app) as client:
        saved = client.post(
            "/api/settings/llm-profiles",
            json={
                "name": "本地兼容接口",
                "base_url": "https://llm.example.test/v1",
                "api_key": TEST_KEY,
                "model": "compatible-chat-model",
            },
        )
        assert saved.status_code == 201
        profile = saved.json()["data"]
        assert profile["has_api_key"] is True
        assert "api_key" not in profile

        tested = client.post(f"/api/settings/llm-profiles/{profile['id']}/test")
        assert tested.status_code == 200
        assert tested.json()["data"]["ok"] is True

        listed = client.get("/api/settings/llm-profiles")
        assert listed.status_code == 200

    persisted = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in tmp_path.rglob("*")
        if path.is_file() and path.suffix in {".json", ".log"}
    )
    combined = persisted + caplog.text + saved.text + tested.text + listed.text
    assert TEST_KEY not in combined


@pytest.mark.parametrize(
    ("base_url", "kind", "expected_code"),
    [
        ("not-a-url", "ok", "llm_invalid_base_url"),
        ("https://llm.example.test/v1", "unauthorized", "llm_authentication_failed"),
        ("https://llm.example.test/v1", "bad_model", "llm_model_not_found"),
        ("https://llm.example.test/v1", "empty", "llm_empty_response"),
        ("https://llm.example.test/v1", "truncated", "llm_invalid_response"),
    ],
)
def test_client_maps_connection_failures_to_stable_problem_codes(
    base_url: str, kind: str, expected_code: str
) -> None:
    client = LlmClient(transport=_openai_transport(kind))

    with pytest.raises(LlmIntegrationError) as captured:
        client.test_connection(base_url=base_url, api_key=TEST_KEY, model="bad-or-good")

    assert captured.value.code == expected_code
    assert TEST_KEY not in str(captured.value)


def test_client_maps_timeout_without_leaking_key() -> None:
    def timeout(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out with hidden credentials")

    client = LlmClient(transport=httpx.MockTransport(timeout), timeout_seconds=0.01)

    with pytest.raises(LlmIntegrationError) as captured:
        client.test_connection(
            base_url="https://llm.example.test/v1", api_key=TEST_KEY, model="model"
        )

    assert captured.value.code == "llm_timeout"
    assert TEST_KEY not in str(captured.value)
