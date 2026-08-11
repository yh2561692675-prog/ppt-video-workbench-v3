from __future__ import annotations

import sqlite3
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from peripheral_contracts import ActionRequest, JobEnvelope
from peripheral_contracts.versioning import UnsupportedSchemaVersion
from pydantic import ValidationError

from peripheral_host.artifact_stream import get_streamable_artifact, stream_verified_file
from peripheral_host.database import DatabaseIntegrityError, DatabaseMigrationError
from peripheral_host.errors import (
    ArtifactIntegrityError,
    ArtifactPublishError,
    WorkspacePathError,
)
from peripheral_host.module_runner import ModuleNotRegistered
from peripheral_host.repositories import ArtifactRecord, ConcurrentTransitionError
from peripheral_host.scheduler import Scheduler
from peripheral_host.service import InvalidJobAction, JobNotFound, JobService

COMPONENT_VERSION = "0.1.0"
MAX_REQUEST_BODY_BYTES = 1024 * 1024

_USER_MESSAGES = {
    "ARTIFACT_HASH_MISMATCH": "输入文件校验失败，请重新选择源文件。",
    "INVALID_INPUT": "请求内容无效，请检查后重试。",
    "INVALID_JOB_ACTION": "当前任务状态不允许执行此操作。",
    "JOB_NOT_FOUND": "未找到指定任务。",
    "CONFLICTING_CONTENT_LENGTH": "请求长度标头无效。",
    "REQUEST_BODY_TOO_LARGE": "请求内容超过允许的大小。",
    "STORAGE_UNAVAILABLE": "外围存储暂不可用，请稍后重试。",
    "UNSUPPORTED_MEDIA_TYPE": "请求必须使用 application/json。",
    "UNSUPPORTED_SCHEMA_VERSION": "协议版本不受支持，请升级客户端。",
    "WORKSPACE_PATH_REJECTED": "工作区文件路径无效。",
    "INTERNAL_ERROR": "外围服务发生内部错误，请稍后重试。",
}


def create_internal_app(*, service: JobService, scheduler: Scheduler) -> FastAPI:
    app = FastAPI(
        title="PPT Video Workbench Peripheral Host",
        version=COMPONENT_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.job_service = service
    app.state.scheduler = scheduler

    @app.middleware("http")
    async def correlation_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.state.correlation_id = str(uuid4())
        rejected = await _request_security_error(request)
        if rejected is not None:
            rejected.headers["X-Correlation-ID"] = request.state.correlation_id
            return rejected
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = request.state.correlation_id
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        code = "INVALID_INPUT"
        for item in error.errors():
            if "schema_version" in item.get("loc", ()):
                code = "UNSUPPORTED_SCHEMA_VERSION"
                break
        return _error_response(request, status.HTTP_422_UNPROCESSABLE_CONTENT, code)

    @app.exception_handler(UnsupportedSchemaVersion)
    async def unsupported_schema_handler(
        request: Request,
        _error: UnsupportedSchemaVersion,
    ) -> JSONResponse:
        return _error_response(
            request,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "UNSUPPORTED_SCHEMA_VERSION",
        )

    @app.exception_handler(JobNotFound)
    async def not_found_handler(request: Request, _error: JobNotFound) -> JSONResponse:
        return _error_response(request, status.HTTP_404_NOT_FOUND, "JOB_NOT_FOUND")

    @app.exception_handler(InvalidJobAction)
    @app.exception_handler(ConcurrentTransitionError)
    async def conflict_handler(request: Request, _error: Exception) -> JSONResponse:
        return _error_response(request, status.HTTP_409_CONFLICT, "INVALID_JOB_ACTION")

    @app.exception_handler(ArtifactIntegrityError)
    async def integrity_handler(
        request: Request,
        _error: ArtifactIntegrityError,
    ) -> JSONResponse:
        return _error_response(
            request,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "ARTIFACT_HASH_MISMATCH",
        )

    @app.exception_handler(WorkspacePathError)
    async def workspace_path_handler(
        request: Request,
        _error: WorkspacePathError,
    ) -> JSONResponse:
        return _error_response(
            request,
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "WORKSPACE_PATH_REJECTED",
        )

    for invalid_type in (
        ArtifactPublishError,
        ModuleNotRegistered,
        ValidationError,
        ValueError,
    ):
        app.add_exception_handler(invalid_type, _invalid_input_handler)

    for storage_type in (
        sqlite3.Error,
        DatabaseIntegrityError,
        DatabaseMigrationError,
    ):
        app.add_exception_handler(storage_type, _storage_handler)

    @app.exception_handler(Exception)
    async def internal_error_handler(request: Request, _error: Exception) -> JSONResponse:
        return _error_response(
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_ERROR",
        )

    @app.post("/internal/v1/jobs")
    async def submit_job(envelope: JobEnvelope, response: Response) -> dict[str, object]:
        result = service.submit_job(envelope)
        response.status_code = status.HTTP_202_ACCEPTED if result.created else status.HTTP_200_OK
        return {
            "job_id": str(result.job_id),
            "status": result.status.value,
            "created": result.created,
        }

    @app.get("/internal/v1/jobs/{job_id}")
    async def get_job(job_id: UUID) -> dict[str, Any]:
        return service.get_job_status(job_id).model_dump(mode="json")

    @app.get("/internal/v1/jobs/{job_id}/artifacts")
    async def list_artifacts(job_id: UUID) -> list[dict[str, object]]:
        return [_artifact_json(item) for item in service.list_artifacts(job_id)]

    @app.get("/internal/v1/jobs/{job_id}/artifacts/{artifact_id}/content")
    async def stream_artifact(job_id: UUID, artifact_id: UUID) -> StreamingResponse:
        record, path = get_streamable_artifact(service, job_id, artifact_id)
        return StreamingResponse(
            stream_verified_file(path, record),
            media_type="application/octet-stream",
            headers={
                "Content-Length": str(record.size_bytes),
                "Digest": f"sha-256={record.sha256}",
                "X-Artifact-Kind": record.kind,
            },
        )

    @app.post("/internal/v1/jobs/{job_id}/actions")
    async def request_action(job_id: UUID, action: ActionRequest) -> dict[str, Any]:
        return service.request_action(job_id, action).model_dump(mode="json")

    @app.get("/internal/v1/health")
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "schema_version": "1.0",
            "component_version": COMPONENT_VERSION,
        }

    return app


async def _request_security_error(request: Request) -> JSONResponse | None:
    if request.method != "POST" or not request.url.path.startswith("/internal/v1/jobs"):
        return None
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().lower()
    if media_type != "application/json":
        return _error_response(
            request,
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "UNSUPPORTED_MEDIA_TYPE",
        )
    content_lengths: list[str] = []
    for name, value in request.scope.get("headers", []):
        if name.lower() == b"content-length":
            content_lengths.extend(
                item.strip() for item in value.decode("ascii", errors="ignore").split(",")
            )
    if content_lengths and (len(content_lengths) != 1 or not content_lengths[0].isdigit()):
        return _error_response(
            request,
            status.HTTP_400_BAD_REQUEST,
            "CONFLICTING_CONTENT_LENGTH",
        )
    if content_lengths and int(content_lengths[0]) > MAX_REQUEST_BODY_BYTES:
        return _error_response(
            request,
            status.HTTP_413_CONTENT_TOO_LARGE,
            "REQUEST_BODY_TOO_LARGE",
        )
    if len(await request.body()) > MAX_REQUEST_BODY_BYTES:
        return _error_response(
            request,
            status.HTTP_413_CONTENT_TOO_LARGE,
            "REQUEST_BODY_TOO_LARGE",
        )
    return None


async def _invalid_input_handler(request: Request, _error: Exception) -> JSONResponse:
    return _error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "INVALID_INPUT",
    )


async def _storage_handler(request: Request, _error: Exception) -> JSONResponse:
    return _error_response(
        request,
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "STORAGE_UNAVAILABLE",
        retryable=True,
    )


def _error_response(
    request: Request,
    http_status: int,
    code: str,
    *,
    retryable: bool = False,
) -> JSONResponse:
    correlation_id = getattr(request.state, "correlation_id", str(uuid4()))
    return JSONResponse(
        status_code=http_status,
        content={
            "error": {
                "code": code,
                "message": _USER_MESSAGES[code],
                "retryable": retryable,
                "correlation_id": correlation_id,
            }
        },
    )


def _artifact_json(record: ArtifactRecord) -> dict[str, object]:
    return {
        "artifact_id": str(record.artifact_id),
        "job_id": str(record.job_id),
        "project_id": str(record.project_id),
        "logical_name": record.logical_name,
        "kind": record.kind,
        "relative_path": record.relative_path,
        "version": record.version,
        "size_bytes": record.size_bytes,
        "sha256": record.sha256,
        "verified_at": record.verified_at.isoformat().replace("+00:00", "Z"),
        "is_current": record.is_current,
    }
