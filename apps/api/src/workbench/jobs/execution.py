from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Protocol
from uuid import UUID

from workbench.domain.enums import JobStatus, JobType

from .checkpoint import Checkpoint, CheckpointStore, JobContext
from .repository import JobRepository


class RenderPauseRequested(RuntimeError):
    pass


class RenderCancelled(RuntimeError):
    pass


class RenderExecutionContext(Protocol):
    job_id: UUID | None
    input_fingerprint: str | None

    def checkpoint(
        self,
        *,
        stage: str,
        progress: float,
        message: str,
        artifacts: Iterable[Path] = (),
        payload: Mapping[str, object] | None = None,
    ) -> None: ...

    def raise_if_cancelled(self) -> None: ...

    def pause_if_requested(self) -> None: ...

    def heartbeat(self) -> None: ...


class InlineRenderExecutionContext:
    job_id = None
    input_fingerprint = None

    def checkpoint(
        self,
        *,
        stage: str,
        progress: float,
        message: str,
        artifacts: Iterable[Path] = (),
        payload: Mapping[str, object] | None = None,
    ) -> None:
        return None

    def raise_if_cancelled(self) -> None:
        return None

    def pause_if_requested(self) -> None:
        return None

    def heartbeat(self) -> None:
        return None

    @property
    def cancel_requested(self) -> bool:
        return False


class PersistentRenderExecutionContext:
    def __init__(
        self,
        *,
        job_id: UUID,
        project_dir: Path,
        repository: JobRepository,
        input_fingerprint: str | None,
        checkpoint_store: CheckpointStore | None = None,
    ) -> None:
        self.job_id = job_id
        self.project_dir = project_dir.resolve()
        self.repository = repository
        self.input_fingerprint = input_fingerprint
        self.store = checkpoint_store or CheckpointStore(self.project_dir)
        self._job_context = JobContext(
            job_id,
            self.project_dir,
            JobType.EXPORT_PACKAGE,
            checkpoint_store=self.store,
        )

    @property
    def cancel_requested(self) -> bool:
        return self.repository.get(self.job_id).status in {
            JobStatus.CANCEL_REQUESTED,
            JobStatus.CANCELLED,
        }

    def checkpoint(
        self,
        *,
        stage: str,
        progress: float,
        message: str,
        artifacts: Iterable[Path] = (),
        payload: Mapping[str, object] | None = None,
    ) -> None:
        data = {"stage": stage, "message": message}
        if payload:
            data.update(payload)
        self._job_context.checkpoint(progress, data, artifacts)
        self.repository.update_progress(
            self.job_id,
            progress,
            stage=stage,
            message=message,
            payload=data,
        )

    def raise_if_cancelled(self) -> None:
        if self.cancel_requested:
            raise RenderCancelled("render job cancellation requested")

    def pause_if_requested(self) -> None:
        self.raise_if_cancelled()
        if self.repository.get(self.job_id).status is JobStatus.PAUSE_REQUESTED:
            self.repository.mark_paused(self.job_id)
            raise RenderPauseRequested("render job pause requested")

    def heartbeat(self) -> None:
        self.repository.heartbeat(self.job_id)

    def restore(self, verify: bool = True) -> Checkpoint | None:
        return self.store.restore(self.job_id, verify=verify)
