from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx


class LlmIntegrationError(Exception):
    def __init__(self, code: str, message: str, action: str) -> None:
        super().__init__(message)
        self.code = code
        self.action = action


class LlmClient:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._transport = transport
        self._timeout = timeout_seconds

    def test_connection(self, *, base_url: str, api_key: str, model: str) -> str:
        return self.complete(
            base_url=base_url,
            api_key=api_key,
            model=model,
            messages=[{"role": "user", "content": "Reply with OK."}],
            max_tokens=8,
        )

    def complete(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
    ) -> str:
        endpoint = _chat_completions_endpoint(base_url)
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        try:
            with httpx.Client(transport=self._transport, timeout=self._timeout) as client:
                response = client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=payload,
                )
        except httpx.TimeoutException as error:
            raise LlmIntegrationError(
                "llm_timeout", "模型接口响应超时", "请检查网络或适当增加超时时间后重试"
            ) from error
        except httpx.HTTPError as error:
            raise LlmIntegrationError(
                "llm_unavailable", "无法连接模型接口", "请检查 Base URL 与网络连接"
            ) from error

        if response.status_code in {401, 403}:
            raise LlmIntegrationError(
                "llm_authentication_failed", "模型接口鉴权失败", "请重新填写有效的 API Key"
            )
        if response.status_code == 404 or (
            response.status_code == 400 and "model" in response.text.lower()
        ):
            raise LlmIntegrationError(
                "llm_model_not_found", "模型名称不可用", "请核对服务商支持的模型名称"
            )
        if response.is_error:
            raise LlmIntegrationError(
                "llm_request_failed", "模型接口拒绝请求", "请检查接口配置后重试"
            )

        try:
            body = response.json()
            choices = body.get("choices", [])
            if not choices:
                raise LlmIntegrationError(
                    "llm_empty_response", "模型返回了空结果", "请重试或检查模型服务状态"
                )
            content = choices[0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise LlmIntegrationError(
                    "llm_empty_response", "模型返回了空结果", "请重试或检查模型服务状态"
                )
            return content
        except LlmIntegrationError:
            raise
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise LlmIntegrationError(
                "llm_invalid_response", "模型响应格式不完整", "请检查接口兼容性或稍后重试"
            ) from error


def _chat_completions_endpoint(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise LlmIntegrationError(
            "llm_invalid_base_url", "Base URL 格式无效", "请输入完整的 HTTP 或 HTTPS 地址"
        )
    return f"{base_url.rstrip('/')}/chat/completions"
