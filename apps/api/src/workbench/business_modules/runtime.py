from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from peripheral_contracts import (
    BusinessArtifact,
    BusinessResultManifest,
    ErrorCategory,
    ErrorDetail,
    EventEnvelope,
    JobEnvelope,
    JobResult,
    OutputArtifact,
)
from pydantic import JsonValue

Handler = Callable[[JobEnvelope, Path], "BusinessExecution"]
_SECRET_PATTERN = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")
_PATH_PATTERN = re.compile(r"(?i)(?:[A-Z]:\\|/)[^\s]+")


@dataclass(frozen=True, slots=True)
class StagedArtifact:
    logical_name: str
    kind: str
    path: Path


@dataclass(frozen=True, slots=True)
class BusinessExecution:
    business_result: BusinessResultManifest
    artifacts: tuple[StagedArtifact, ...] = ()


class BusinessModuleError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        category: ErrorCategory,
        code: str,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.code = code
        self.retryable = retryable


def business_input_fingerprint(job: JobEnvelope) -> str:
    supplied = job.parameters.get("input_fingerprint")
    if isinstance(supplied, str) and re.fullmatch(r"[0-9a-f]{64}", supplied):
        return supplied
    return hashlib.sha256(job.model_dump_json().encode("utf-8")).hexdigest()


def business_parameters(job: JobEnvelope) -> dict[str, JsonValue]:
    metadata = {
        "module_id",
        "project_revision",
        "runtime_version",
        "affected_page_ids",
        "input_fingerprint",
        "project_snapshot_sha256",
    }
    return {key: value for key, value in job.parameters.items() if key not in metadata}


def execute_business_handler(
    job: JobEnvelope,
    attempt_root: Path,
    result_path: Path,
    module_id: str,
    handler: Handler,
) -> JobResult:
    attempt_root.mkdir(parents=True, exist_ok=True)
    _emit(job, module_id, "module.started", "info", {"progress": 0})
    try:
        execution = handler(job, attempt_root)
        outputs: list[OutputArtifact] = []
        business_artifacts: list[BusinessArtifact] = []
        for staged in execution.artifacts:
            _validate_staged(staged.path, attempt_root)
            size, digest = _file_digest(staged.path)
            business_artifacts.append(
                BusinessArtifact(
                    logical_name=staged.logical_name,
                    kind=staged.kind,
                    size_bytes=size,
                    sha256=digest,
                )
            )
            outputs.append(
                OutputArtifact(
                    logical_name=staged.logical_name,
                    kind=staged.kind,
                    staged_path=staged.path.relative_to(attempt_root).as_posix(),
                    size_bytes=size,
                    sha256=digest,
                )
            )
        result = execution.business_result.model_copy(
            update={"artifacts": tuple(business_artifacts)}
        )
        _write_atomic(attempt_root / "business-result.json", result.model_dump_json())
        result_size, result_digest = _file_digest(attempt_root / "business-result.json")
        outputs.append(
            OutputArtifact(
                logical_name="business-result",
                kind="json",
                staged_path="business-result.json",
                size_bytes=result_size,
                sha256=result_digest,
            )
        )
        _emit(job, module_id, "module.progress", "info", {"progress": 100})
        completed = JobResult(
            schema_version="1.0", job_id=job.job_id, outcome="succeeded", outputs=tuple(outputs)
        )
        _write_atomic(result_path, completed.model_dump_json())
        _emit(job, module_id, "module.completed", "info", {"progress": 100, "outcome": "succeeded"})
        return completed
    except Exception as error:
        detail = _error_detail(error)
        failed = JobResult(
            schema_version="1.0",
            job_id=job.job_id,
            outcome="failed",
            error=ErrorDetail(
                category=detail.category,
                code=detail.code,
                message=_safe_message(str(error)),
                retryable=detail.retryable,
            ),
        )
        _write_atomic(result_path, failed.model_dump_json())
        _emit(job, module_id, "module.completed", "error", {"progress": 0, "outcome": "failed"})
        return failed


def _validate_staged(path: Path, root: Path) -> None:
    resolved_root = root.resolve()
    if path.is_symlink():
        raise ValueError("staged artifact cannot be a symlink")
    resolved = path.resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError("staged artifact escapes attempt root") from error
    if not resolved.is_file():
        raise ValueError("staged artifact is not a regular file")


def _file_digest(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def _write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(content + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)


def _safe_message(message: str) -> str:
    redacted = _SECRET_PATTERN.sub(r"\1[REDACTED]", message)
    redacted = _PATH_PATTERN.sub("[PATH]", redacted)
    return redacted[:512] or "module execution failed"


def _error_detail(error: Exception) -> BusinessModuleError:
    if isinstance(error, BusinessModuleError):
        return error
    if isinstance(error, ValueError):
        return BusinessModuleError(
            str(error),
            category=ErrorCategory.INPUT,
            code="MODULE_INPUT_INVALID",
            retryable=False,
        )
    if isinstance(error, OSError):
        return BusinessModuleError(
            str(error),
            category=ErrorCategory.STORAGE,
            code="MODULE_STORAGE_ERROR",
            retryable=True,
        )
    return BusinessModuleError(
        str(error),
        category=ErrorCategory.INTERNAL,
        code="MODULE_INTERNAL_ERROR",
        retryable=False,
    )


def _emit(
    job: JobEnvelope,
    module_id: str,
    event_type: str,
    severity: Literal["debug", "info", "warning", "error"],
    data: dict[str, JsonValue],
) -> None:
    event = EventEnvelope(
        schema_version="1.0",
        event_id=uuid4(),
        job_id=job.job_id,
        project_id=job.project_id,
        source=module_id,
        event_type=event_type,
        severity=severity,
        occurred_at=datetime.now(UTC),
        data=data,
    )
    print(event.model_dump_json(), flush=True)
