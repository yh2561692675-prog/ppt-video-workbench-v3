from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, Lock, Thread
from uuid import UUID

from peripheral_contracts import ErrorCategory, ErrorDetail, JobStatus

from peripheral_host.module_runner import ModuleExecutionResult, ModuleRunner
from peripheral_host.repositories import JobRecord
from peripheral_host.service import JobService

BACKOFF_SECONDS = (5, 30, 120)
MAX_AUTOMATIC_ATTEMPTS = 3


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Scheduler:
    def __init__(
        self,
        *,
        service: JobService,
        runner: ModuleRunner,
        clock: Callable[[], datetime] = _utc_now,
        poll_interval_seconds: float = 0.05,
    ) -> None:
        self.service = service
        self.runner = runner
        self.clock = clock
        self.poll_interval_seconds = poll_interval_seconds
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._run_lock = Lock()
        self._active_job_id: UUID | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._loop, name="peripheral-scheduler", daemon=True)
        self._thread.start()

    def stop(self, *, grace_seconds: float = 10.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=grace_seconds)
            if self._thread.is_alive() and self._active_job_id is not None:
                current = self.service.repositories.jobs.get(self._active_job_id)
                if current is not None and current.status is JobStatus.RUNNING:
                    self.service.state_machine.transition(
                        current.job_id,
                        JobStatus.RUNNING,
                        JobStatus.CANCELLING,
                        event_data={"requested_by": "peripheral-host-shutdown"},
                    )
                self._thread.join(timeout=3.0)

    def run_once(self) -> bool:
        with self._run_lock:
            now = self.clock()
            self.service.requeue_due_retries(now)
            record = self.service.claim_next(now)
            if record is None:
                return False
            self._run_claimed(record)
            return True

    def recover_on_startup(self) -> int:
        recovered = 0
        now = self.clock()
        for record in self.service.repositories.jobs.list_by_status(JobStatus.RUNNING):
            error = ErrorDetail(
                category=ErrorCategory.PROCESSING,
                code="HOST_RESTARTED_DURING_ATTEMPT",
                message="Peripheral host restarted during an attempt",
                retryable=True,
            )
            self.service.state_machine.transition(
                record.job_id,
                JobStatus.RUNNING,
                JobStatus.RETRY_WAIT,
                next_attempt_at=now,
                last_error_json=error.model_dump_json(),
            )
            recovered += 1
        for record in self.service.repositories.jobs.list_by_status(JobStatus.CANCELLING):
            attempt = self.service.repositories.attempts.latest_for_job(record.job_id)
            if attempt is not None:
                _clean_attempt_temporary_files(attempt.root)
            self.service.state_machine.transition(
                record.job_id,
                JobStatus.CANCELLING,
                JobStatus.CANCELLED,
            )
            recovered += 1
        return recovered

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            worked = self.run_once()
            if not worked:
                self._stop_event.wait(0.25)

    def _run_claimed(self, record: JobRecord) -> None:
        self._active_job_id = record.job_id
        try:
            self._run_claimed_active(record)
        finally:
            self._active_job_id = None

    def _run_claimed_active(self, record: JobRecord) -> None:
        attempt_root = (
            self.service.workspace_root
            / "projects"
            / str(record.project_id)
            / "state"
            / "jobs"
            / str(record.job_id)
            / "attempts"
            / f"{record.current_attempt:04d}"
        )
        attempt = self.service.repositories.attempts.create(
            record.job_id,
            record.current_attempt,
            attempt_root,
        )
        current = self.service.repositories.jobs.get(record.job_id)
        if current is not None and current.status is JobStatus.CANCELLING:
            self._finish_cancelled(record, attempt.attempt_id, exit_code=None)
            return

        running = self.runner.start(record.envelope, attempt)
        started_at = time.monotonic()
        timeout_seconds = running.registered_module.manifest.max_runtime_seconds
        while running.process.poll() is None:
            current = self.service.repositories.jobs.get(record.job_id)
            if current is not None and current.status is JobStatus.CANCELLING:
                self.runner.cancel(running, grace_seconds=2.0)
                execution = self.runner.collect(running)
                self._store_module_events(execution)
                self._finish_cancelled(record, attempt.attempt_id, execution.exit_code)
                return
            if time.monotonic() - started_at >= timeout_seconds:
                self.runner.cancel(running, grace_seconds=2.0)
                execution = self.runner.collect(running, timed_out=True)
                self._store_module_events(execution)
                error = ErrorDetail(
                    category=ErrorCategory.PROCESSING,
                    code="MODULE_TIMEOUT",
                    message="Peripheral module exceeded its runtime limit",
                    retryable=True,
                )
                self._finish_failure(record, attempt.attempt_id, execution, error)
                return
            time.sleep(self.poll_interval_seconds)

        execution = self.runner.collect(running)
        self._store_module_events(execution)
        if (
            execution.exit_code == 0
            and execution.validation_error is None
            and execution.result is not None
            and execution.result.outcome == "succeeded"
        ):
            self.service.complete_attempt(
                record.job_id,
                attempt.attempt_id,
                execution.result,
            )
            return
        if execution.result is not None and execution.result.error is not None:
            error = execution.result.error
        else:
            error = ErrorDetail(
                category=ErrorCategory.INTERNAL,
                code="MODULE_CONTRACT_VIOLATION",
                message=execution.validation_error or "Peripheral module failed",
                retryable=False,
            )
        self._finish_failure(record, attempt.attempt_id, execution, error)

    def _store_module_events(self, execution: ModuleExecutionResult) -> None:
        for event in execution.events:
            self.service.repositories.events.append(event)

    def _finish_failure(
        self,
        record: JobRecord,
        attempt_id: UUID,
        execution: ModuleExecutionResult,
        error: ErrorDetail,
    ) -> None:
        should_retry = error.retryable and record.current_attempt < MAX_AUTOMATIC_ATTEMPTS
        target = JobStatus.RETRY_WAIT if should_retry else JobStatus.FAILED
        next_attempt_at = None
        if should_retry:
            next_attempt_at = self.clock() + timedelta(
                seconds=BACKOFF_SECONDS[record.current_attempt - 1]
            )
        database = self.service.repositories.jobs.database
        with database.transaction(immediate=True) as connection:
            self.service.repositories.attempts.finish(
                attempt_id,
                status="failed",
                exit_code=execution.exit_code,
                connection=connection,
            )
            self.service.state_machine.transition(
                record.job_id,
                JobStatus.RUNNING,
                target,
                connection=connection,
                next_attempt_at=next_attempt_at,
                last_error_json=error.model_dump_json(),
                event_data={"error_code": error.code},
            )

    def _finish_cancelled(
        self,
        record: JobRecord,
        attempt_id: UUID,
        exit_code: int | None,
    ) -> None:
        database = self.service.repositories.jobs.database
        with database.transaction(immediate=True) as connection:
            self.service.repositories.attempts.finish(
                attempt_id,
                status="cancelled",
                exit_code=exit_code,
                connection=connection,
            )
            self.service.state_machine.transition(
                record.job_id,
                JobStatus.CANCELLING,
                JobStatus.CANCELLED,
                connection=connection,
            )


def _clean_attempt_temporary_files(root: Path) -> None:
    if not root.is_dir():
        return
    for candidate in root.rglob("*.tmp"):
        if candidate.is_file() and not candidate.is_symlink():
            candidate.unlink()
