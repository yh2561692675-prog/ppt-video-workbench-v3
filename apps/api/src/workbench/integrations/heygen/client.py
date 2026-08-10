from __future__ import annotations

import json as json_module
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class HeyGenIntegrationError(RuntimeError):
    def __init__(self, code: str, message: str, action: str) -> None:
        super().__init__(message)
        self.code = code
        self.action = action


class HeyGenVoice(BaseModel):
    model_config = ConfigDict(extra="ignore")

    voice_id: str
    name: str
    language: str = ""
    gender: str = ""
    support_pause: bool = False
    support_locale: bool = False
    preview_audio_url: HttpUrl | None = None


class SpeechResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    audio_url: HttpUrl
    duration: float = Field(ge=0)
    request_id: str = ""


@dataclass(frozen=True)
class DownloadedAudio:
    content: bytes
    content_type: str


class HeyGenClient:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout_seconds: float = 30,
        speech_timeout_seconds: float = 90,
        log_path: Path | None = None,
        retry_backoff_seconds: float = 2,
        speech_max_attempts: int = 3,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if speech_max_attempts < 1:
            raise ValueError("speech_max_attempts must be positive")
        self.transport = transport
        self.timeout_seconds = timeout_seconds
        self.speech_timeout_seconds = speech_timeout_seconds
        self.log_path = log_path
        self.retry_backoff_seconds = retry_backoff_seconds
        self.speech_max_attempts = speech_max_attempts
        self.sleeper = sleeper

    def list_voices(
        self, api_key: str, base_url: str = "https://api.heygen.com"
    ) -> list[HeyGenVoice]:
        response = self._request(
            "GET",
            f"{base_url.rstrip('/')}/v3/voices",
            api_key,
            params={"type": "private", "engine": "starfish", "limit": "100"},
        )
        payload = response.json()
        return [HeyGenVoice.model_validate(item) for item in payload.get("data", [])]

    def generate_speech(
        self,
        api_key: str,
        *,
        text: str,
        voice_id: str,
        speed: float = 1,
        language: str = "zh",
        base_url: str = "https://api.heygen.com",
    ) -> SpeechResult:
        for attempt in range(1, self.speech_max_attempts + 1):
            started = time.perf_counter()
            try:
                response = self._request(
                    "POST",
                    f"{base_url.rstrip('/')}/v3/voices/speech",
                    api_key,
                    timeout_seconds=self.speech_timeout_seconds,
                    json={
                        "text": text,
                        "voice_id": voice_id,
                        "input_type": "text",
                        "speed": speed,
                        "language": language,
                    },
                )
                speech = SpeechResult.model_validate(response.json().get("data"))
                self._write_attempt_log("success", attempt, started)
                return speech
            except HeyGenIntegrationError as error:
                retryable = error.code in {
                    "heygen_timeout",
                    "heygen_network_error",
                    "heygen_service_error",
                }
                if retryable and attempt < self.speech_max_attempts:
                    self._write_attempt_log("retry", attempt, started, error.code)
                    self.sleeper(self.retry_backoff_seconds * 2 ** (attempt - 1))
                    continue
                self._write_attempt_log("failure", attempt, started, error.code)
                raise
        raise AssertionError("speech retry loop unexpectedly exhausted")

    def download(self, url: str) -> DownloadedAudio:
        response = self._request("GET", url, None)
        if not response.content:
            raise HeyGenIntegrationError(
                "heygen_empty_audio", "HeyGen 返回了空音频", "请重试当前页面"
            )
        return DownloadedAudio(
            content=response.content,
            content_type=response.headers.get("Content-Type", "application/octet-stream"),
        )

    def _request(
        self,
        method: str,
        url: str,
        api_key: str | None,
        *,
        params: Mapping[str, str] | None = None,
        json: dict[str, object] | None = None,
        timeout_seconds: float | None = None,
    ) -> httpx.Response:
        try:
            with httpx.Client(
                transport=self.transport,
                timeout=timeout_seconds or self.timeout_seconds,
                follow_redirects=True,
            ) as client:
                response = client.request(
                    method,
                    url,
                    headers={"x-api-key": api_key} if api_key else None,
                    params=params,
                    json=json,
                )
        except httpx.TimeoutException as error:
            raise HeyGenIntegrationError(
                "heygen_timeout", "HeyGen 请求超时", "请稍后仅重试当前页面"
            ) from error
        except httpx.HTTPError as error:
            raise HeyGenIntegrationError(
                "heygen_network_error", "无法连接 HeyGen", "请检查网络后重试"
            ) from error
        if response.is_success:
            return response
        try:
            remote_code = str(response.json().get("error", {}).get("code", ""))
        except ValueError:
            remote_code = ""
        if response.status_code == 401 or remote_code == "authentication_failed":
            code, message, action = (
                "heygen_authentication_failed",
                "HeyGen API Key 无效或已过期",
                "请更新 HeyGen 凭证",
            )
        elif response.status_code == 429 or remote_code == "rate_limit_exceeded":
            code, message, action = (
                "heygen_rate_limited",
                "HeyGen 请求频率受限",
                "请按提示稍后仅重试当前页面",
            )
        elif response.status_code == 402 or any(
            value in remote_code for value in ("credit", "quota", "insufficient")
        ):
            code, message, action = (
                "heygen_quota_exhausted",
                "HeyGen 额度不足",
                "请补充额度后继续，已成功页面不会重做",
            )
        else:
            code, message, action = (
                "heygen_service_error",
                "HeyGen 服务暂时失败",
                "请稍后仅重试当前页面",
            )
        raise HeyGenIntegrationError(code, message, action)

    def _write_attempt_log(
        self, event: str, attempt: int, started: float, error_code: str | None = None
    ) -> None:
        if self.log_path is None:
            return
        record: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "service_pid": os.getpid(),
            "operation": "heygen_speech",
            "event": event,
            "attempt": attempt,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }
        if error_code is not None:
            record["error_code"] = error_code
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json_module.dumps(record, ensure_ascii=False) + "\n")
