from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from threading import Event, Lock, Thread
from time import sleep
from uuid import UUID

from workbench.domain.enums import JobStatus, JobType
from workbench.domain.models import JobRecord

from .registry import JobExecutorRegistry
from .repository import JobRepository


class RenderJobWorker:
    def __init__(
        self,
        repository: JobRepository,
        handler: Callable[[JobRecord], None] | None = None,
        *,
        enabled: bool = True,
        poll_interval: float = 0.5,
        job_types: Sequence[JobType] | None = None,
        handlers: Mapping[JobType, Callable[[JobRecord], None]] | None = None,
        registry: JobExecutorRegistry | None = None,
        worker_id: str = "render-worker",
        runtime_fingerprint: str | None = None,
    ) -> None:
        self.repository = repository
        self.handler = handler
        self.enabled = enabled
        self.poll_interval = poll_interval
        self._stop_event = Event()
        self._wake_event = Event()
        self._thread: Thread | None = None
        self._active_job_id: UUID | None = None
        self._active_lock = Lock()
        self.job_types = tuple(job_types or (JobType.EXPORT_PACKAGE,))
        self.registry = registry or JobExecutorRegistry()
        if handler is not None:
            self.registry.replace(JobType.EXPORT_PACKAGE, handler)
        for job_type, job_handler in (handlers or {}).items():
            self.registry.replace(job_type, job_handler)
        self.registry.validate(self.job_types)
        self.worker_id = worker_id
        self.runtime_fingerprint = runtime_fingerprint
        self._next_type = 0

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def active_job_id(self) -> UUID | None:
        with self._active_lock:
            return self._active_job_id

    def start(self) -> None:
        if not self.enabled or self.is_alive:
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._run, name="render-job-worker", daemon=True)
        self._thread.start()

    def wake(self) -> None:
        self._wake_event.set()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        active_job_id = self.active_job_id
        if active_job_id is not None:
            with suppress(Exception):
                self.repository.request_pause(active_job_id)
        self._wake_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(timeout, 0.0))

    def _run(self) -> None:
        while not self._stop_event.is_set():
            record = self._claim_next()
            if record is None:
                self._wake_event.wait(self.poll_interval)
                self._wake_event.clear()
                continue
            with self._active_lock:
                self._active_job_id = record.id
            try:
                self.registry.get(record.job_type)(record)
            except Exception as error:
                try:
                    current = self.repository.get(record.id)
                    if current.status not in {
                        JobStatus.SUCCEEDED,
                        JobStatus.FAILED,
                        JobStatus.CANCELLED,
                    }:
                        self.repository.fail(record.id, str(error))
                except Exception:
                    pass
            finally:
                with self._active_lock:
                    self._active_job_id = None
                sleep(0)

    def _claim_next(self) -> JobRecord | None:
        if not self.job_types:
            return None
        for offset in range(len(self.job_types)):
            index = (self._next_type + offset) % len(self.job_types)
            job_type = self.job_types[index]
            record = self.repository.claim_next(
                job_type,
                worker_id=self.worker_id,
                runtime_fingerprint=self.runtime_fingerprint,
            )
            if record is not None:
                self._next_type = (index + 1) % len(self.job_types)
                return record
        return None
