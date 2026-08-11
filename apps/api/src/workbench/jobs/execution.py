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
    @property
    def job_id(self) -> UUID | None: ...

    @property
    def input_fingerprint(self) -> str | None: ...

    @property
    def cancel_requested(self) -> bool: ...

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

    def register_temporary_paths(self, paths: Iterable[Path]) -> None: ...


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

    def register_temporary_paths(self, paths: Iterable[Path]) -> None:
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
        job_type: JobType = JobType.EXPORT_PACKAGE,
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
            job_type,
            checkpoint_store=self.store,
        )
        restored = self.store.latest(job_id)
        self._temporary_paths = set(restored.temporary_paths if restored is not None else [])

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
        data: dict[str, object] = {
            "stage": stage,
            "message": message,
            "temporary_paths": sorted(self._temporary_paths),
        }
        if payload:
            data.update(payload)
        checkpoint = self._job_context.checkpoint(progress, data, artifacts)
        self.repository.record_checkpoint(
            self.job_id,
            checkpoint.model_dump(mode="json"),
        )
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

    def register_temporary_paths(self, paths: Iterable[Path]) -> None:
        for path in paths:
            target = path.resolve()
            if self.project_dir not in target.parents:
                raise ValueError("temporary render path escapes project directory")
            self._temporary_paths.add(target.relative_to(self.project_dir).as_posix())
        record = self.repository.get(self.job_id)
        self.checkpoint(
            stage=record.stage,
            progress=record.progress,
            message=record.message,
        )

    def restore(self, verify: bool = True) -> Checkpoint | None:
        return self.store.restore(self.job_id, verify=verify)
