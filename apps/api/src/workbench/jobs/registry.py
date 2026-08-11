from __future__ import annotations

from collections.abc import Callable, Iterable

from workbench.domain.enums import JobType
from workbench.domain.models import JobRecord

JobHandler = Callable[[JobRecord], None]


class JobExecutorRegistry:
    """Explicit mapping from durable JobType to a handler."""

    def __init__(self) -> None:
        self._handlers: dict[JobType, JobHandler] = {}

    def register(self, job_type: JobType, handler: JobHandler) -> None:
        if job_type in self._handlers:
            raise ValueError(f"executor already registered for {job_type.value}")
        self._handlers[job_type] = handler

    def replace(self, job_type: JobType, handler: JobHandler) -> None:
        self._handlers[job_type] = handler

    def get(self, job_type: JobType) -> JobHandler:
        try:
            return self._handlers[job_type]
        except KeyError as error:
            raise KeyError(f"no executor registered for {job_type.value}") from error

    def supported(self) -> tuple[JobType, ...]:
        return tuple(self._handlers)

    def validate(self, job_types: Iterable[JobType]) -> None:
        missing = [job_type.value for job_type in job_types if job_type not in self._handlers]
        if missing:
            raise ValueError(f"missing job executors: {', '.join(missing)}")
