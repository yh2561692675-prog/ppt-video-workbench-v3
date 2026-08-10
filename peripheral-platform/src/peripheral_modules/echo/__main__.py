from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from peripheral_contracts import (
    ErrorCategory,
    ErrorDetail,
    EventEnvelope,
    JobEnvelope,
    JobResult,
    OutputArtifact,
)

from peripheral_modules.echo import EchoParameters


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    arguments = parser.parse_args()

    job = JobEnvelope.model_validate_json(arguments.request.read_text(encoding="utf-8"))
    parameters = EchoParameters.model_validate(job.parameters)
    _emit_event(job, "module.started", {"module": "echo"})
    _delay_with_progress(job, parameters.delay_ms)

    if parameters.fail_mode == "invalid_result":
        _write_json_atomic(
            arguments.result,
            {
                "schema_version": "1.0",
                "job_id": str(job.job_id),
                "outcome": "succeeded",
                "unexpected": True,
            },
        )
        return 0

    if parameters.fail_mode in {"retryable", "permanent"}:
        retryable = parameters.fail_mode == "retryable"
        result = JobResult(
            schema_version="1.0",
            job_id=job.job_id,
            outcome="failed",
            error=ErrorDetail(
                category=(ErrorCategory.PROVIDER if retryable else ErrorCategory.INPUT),
                code=("ECHO_RETRYABLE_FAILURE" if retryable else "ECHO_PERMANENT_FAILURE"),
                message="Echo module injected a controlled failure",
                retryable=retryable,
            ),
        )
        _write_model_atomic(arguments.result, result)
        _emit_event(job, "module.completed", {"outcome": "failed"})
        return 0

    output_path = arguments.result.parent / "echo.txt"
    payload = parameters.text.encode("utf-8")
    _write_bytes_atomic(output_path, payload)
    result = JobResult(
        schema_version="1.0",
        job_id=job.job_id,
        outcome="succeeded",
        outputs=(
            OutputArtifact(
                logical_name="echo-text",
                kind="text",
                staged_path=output_path.name,
                size_bytes=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
            ),
        ),
    )
    _write_model_atomic(arguments.result, result)
    _emit_event(job, "module.completed", {"outcome": "succeeded"})
    return 0


def _delay_with_progress(job: JobEnvelope, delay_ms: int) -> None:
    remaining_ms = delay_ms
    while remaining_ms > 0:
        sleep_ms = min(250, remaining_ms)
        time.sleep(sleep_ms / 1000)
        remaining_ms -= sleep_ms
        progress = 100 if delay_ms == 0 else int((delay_ms - remaining_ms) * 100 / delay_ms)
        _emit_event(job, "module.progress", {"progress": progress})


def _emit_event(job: JobEnvelope, event_type: str, data: dict[str, object]) -> None:
    event = EventEnvelope.model_validate(
        {
            "schema_version": "1.0",
            "event_id": uuid4(),
            "job_id": job.job_id,
            "project_id": job.project_id,
            "source": "echo",
            "event_type": event_type,
            "severity": "info",
            "occurred_at": datetime.now(UTC),
            "data": data,
        }
    )
    print(event.model_dump_json(), flush=True)


def _write_model_atomic(path: Path, model: JobResult) -> None:
    _write_bytes_atomic(path, (model.model_dump_json(indent=2) + "\n").encode())


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    _write_bytes_atomic(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(),
    )


def _write_bytes_atomic(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f"{path.name}.tmp")
    with temporary.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


if __name__ == "__main__":
    raise SystemExit(main())
