from collections.abc import Callable
from threading import Event, Lock
from time import sleep
from uuid import UUID

from workbench.domain.models import JobRecord

from .checkpoint import JobContext
from .repository import JobRepository


class CancellationToken:
    def __init__(self) -> None:
        self._event = Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


class JobRunner:
    def __init__(
        self,
        repository: JobRepository,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self.repository = repository
        self.sleeper = sleeper
        self._consumer_lock = Lock()

    def execute(
        self,
        job_id: UUID,
        handler: Callable[[], None],
        token: CancellationToken | None = None,
        context: JobContext | None = None,
    ) -> JobRecord:
        with self._consumer_lock:
            if (token and token.cancelled) or (context and context.should_cancel):
                return self.repository.pause(job_id)

            record = self.repository.mark_running(job_id)
            while record.attempts < record.max_attempts:
                if (token and token.cancelled) or (context and context.should_cancel):
                    return self.repository.pause(job_id)
                try:
                    handler()
                except Exception as error:
                    record = self.repository.record_attempt(job_id, str(error))
                    if record.attempts >= record.max_attempts:
                        return self.repository.fail(job_id, str(error))
                    self.sleeper(float(2 ** (record.attempts - 1)))
                    continue

                if context and (context.should_pause or context.should_cancel):
                    return self.repository.pause(job_id)
                self.repository.record_attempt(job_id)
                return self.repository.complete(job_id)

            return self.repository.fail(job_id, record.error or "attempt limit reached")

    def recover_job(
        self,
        job_id: UUID,
        handler: Callable[[], None],
        *,
        context: JobContext,
    ) -> JobRecord:
        checkpoint = context.restore()
        if checkpoint is None:
            raise JobRecoveryError(f"no valid checkpoint found for job {job_id}")
        context.query_remote_tasks(checkpoint)
        self.repository.requeue_for_recovery(job_id)
        return self.execute(job_id, handler, context=context)


class JobRecoveryError(RuntimeError):
    pass


def recover_job(
    job_id: UUID,
    handler: Callable[[], None],
    *,
    runner: JobRunner,
    context: JobContext,
) -> JobRecord:
    """Recover a job from its latest verified checkpoint."""

    return runner.recover_job(job_id, handler, context=context)
