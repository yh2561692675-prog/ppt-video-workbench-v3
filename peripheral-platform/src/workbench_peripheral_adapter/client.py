from __future__ import annotations

from typing import Any, Protocol, TypeVar
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError

from workbench_peripheral_adapter.dto import (
    ActionRequestDto,
    ArtifactDto,
    JobStatusDto,
    SubmitJobDto,
    SubmitJobResultDto,
)

UNAVAILABLE_MESSAGE = "外围功能暂不可用，原有视频流程仍可继续使用。"
DtoT = TypeVar("DtoT", bound=BaseModel)


class PeripheralUnavailable(RuntimeError):
    def __init__(self, reason: str = "unavailable") -> None:
        super().__init__(reason)
        self.user_message = UNAVAILABLE_MESSAGE


class PeripheralRequestRejected(RuntimeError):
    def __init__(self, *, status_code: int, code: str, user_message: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.user_message = user_message


class PeripheralClientProtocol(Protocol):
    enabled: bool

    def probe(self) -> bool: ...

    def submit_job(self, request: SubmitJobDto) -> SubmitJobResultDto: ...

    def get_job_status(self, job_id: UUID) -> JobStatusDto: ...

    def list_artifacts(self, job_id: UUID) -> tuple[ArtifactDto, ...]: ...

    def request_action(
        self,
        job_id: UUID,
        request: ActionRequestDto,
    ) -> JobStatusDto: ...


class DisabledPeripheralClient:
    enabled = False

    def probe(self) -> bool:
        return False

    def submit_job(self, request: SubmitJobDto) -> SubmitJobResultDto:
        raise PeripheralUnavailable("peripheral feature is disabled")

    def get_job_status(self, job_id: UUID) -> JobStatusDto:
        raise PeripheralUnavailable("peripheral feature is disabled")

    def list_artifacts(self, job_id: UUID) -> tuple[ArtifactDto, ...]:
        raise PeripheralUnavailable("peripheral feature is disabled")

    def request_action(
        self,
        job_id: UUID,
        request: ActionRequestDto,
    ) -> JobStatusDto:
        raise PeripheralUnavailable("peripheral feature is disabled")


class HttpPeripheralClient:
    enabled = True

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 3.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = _validated_loopback_url(base_url)
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def probe(self) -> bool:
        try:
            payload = self._request("GET", "/internal/v1/health")
        except (PeripheralUnavailable, PeripheralRequestRejected):
            return False
        return (
            isinstance(payload, dict)
            and payload.get("status") == "ok"
            and payload.get("schema_version") == "1.0"
        )

    def submit_job(self, request: SubmitJobDto) -> SubmitJobResultDto:
        payload = self._request(
            "POST",
            "/internal/v1/jobs",
            json=request.model_dump(mode="json"),
        )
        return self._validate(SubmitJobResultDto, payload)

    def get_job_status(self, job_id: UUID) -> JobStatusDto:
        payload = self._request("GET", f"/internal/v1/jobs/{job_id}")
        return self._validate(JobStatusDto, payload)

    def list_artifacts(self, job_id: UUID) -> tuple[ArtifactDto, ...]:
        payload = self._request("GET", f"/internal/v1/jobs/{job_id}/artifacts")
        if not isinstance(payload, list):
            raise PeripheralUnavailable("invalid artifact response")
        artifacts: list[ArtifactDto] = []
        for item in payload:
            if not isinstance(item, dict):
                raise PeripheralUnavailable("invalid artifact response")
            sanitized = {
                key: value
                for key, value in item.items()
                if key not in {"path", "relative_path", "absolute_path"}
            }
            artifacts.append(self._validate(ArtifactDto, sanitized))
        return tuple(artifacts)

    def request_action(
        self,
        job_id: UUID,
        request: ActionRequestDto,
    ) -> JobStatusDto:
        payload = self._request(
            "POST",
            f"/internal/v1/jobs/{job_id}/actions",
            json=request.model_dump(mode="json"),
        )
        return self._validate(JobStatusDto, payload)

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> object:
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                transport=self.transport,
            ) as client:
                response = client.request(method, path, json=json)
        except httpx.RequestError as error:
            raise PeripheralUnavailable(type(error).__name__) from error
        if response.status_code == 503 or response.status_code >= 500:
            raise PeripheralUnavailable(f"host returned {response.status_code}")
        if response.status_code >= 400:
            raise _rejected(response)
        try:
            return response.json()
        except ValueError as error:
            raise PeripheralUnavailable("host returned invalid JSON") from error

    @staticmethod
    def _validate(model: type[DtoT], payload: object) -> DtoT:
        try:
            return model.model_validate(payload)
        except ValidationError as error:
            raise PeripheralUnavailable("host response violated adapter contract") from error


def _rejected(response: httpx.Response) -> PeripheralRequestRejected:
    code = "PERIPHERAL_REQUEST_REJECTED"
    message = "外围请求未能完成，请检查后重试。"
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        error = payload["error"]
        code = str(error.get("code", code))
        message = str(error.get("message", message))
    return PeripheralRequestRejected(
        status_code=response.status_code,
        code=code,
        user_message=message,
    )


def _validated_loopback_url(base_url: str) -> str:
    parsed = urlsplit(base_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("peripheral base URL must be loopback HTTP origin")
    if parsed.port is None:
        raise ValueError("peripheral base URL must include a port")
    return base_url.rstrip("/")
