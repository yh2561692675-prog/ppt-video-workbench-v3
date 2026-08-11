from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from pathlib import Path
from uuid import UUID

from workbench.domain.enums import JobType
from workbench.jobs.checkpoint import Checkpoint, JobContext

PRESENTER_PIPELINE_STAGES = (
    "media_probe",
    "audio_extract",
    "asr_30",
    "asr_70",
    "transcript",
    "match_50",
    "match",
    "anchors",
    "layout",
    "page_render_50",
    "final",
)

PresenterStageProcessor = Callable[[str], Iterable[Path]]


class PresenterPipelineInterrupted(RuntimeError):
    pass


class PresenterPipelineHandler:
    def __init__(self, project_dir: Path, job_id: UUID) -> None:
        self.project_dir = project_dir.resolve()
        self.context = JobContext(job_id, self.project_dir, JobType.PRESENTER_SYNC)

    def run(
        self,
        processor: PresenterStageProcessor,
        *,
        protected_artifacts: Iterable[Path] = (),
        manual_lock_ids: Iterable[str] = (),
        interrupt_after: str | None = None,
    ) -> Checkpoint:
        restored = self.context.restore()
        completed = list(restored.completed_stages if restored else [])
        artifacts = [
            self.project_dir / artifact.relative_path
            for artifact in (restored.artifacts if restored else [])
        ]
        for path in protected_artifacts:
            if path not in artifacts:
                artifacts.append(path)
        latest = restored
        for index, stage in enumerate(PRESENTER_PIPELINE_STAGES, start=1):
            if stage in completed:
                continue
            for path in processor(stage):
                if path not in artifacts:
                    artifacts.append(path)
            completed.append(stage)
            latest = self.context.checkpoint(
                index / len(PRESENTER_PIPELINE_STAGES),
                {
                    "stage": stage,
                    "completed_stages": completed,
                    "manual_lock_ids": sorted(set(manual_lock_ids)),
                    "preserve_manual_locks": True,
                },
                artifacts=artifacts,
            )
            if stage == interrupt_after:
                raise PresenterPipelineInterrupted(stage)
        if latest is None:
            raise RuntimeError("presenter pipeline produced no checkpoint")
        return latest

    def write_artifact(self, relative_path: str, content: bytes) -> Path:
        target = (self.project_dir / relative_path).resolve()
        if self.project_dir not in target.parents:
            raise ValueError("presenter artifact escapes project directory")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        try:
            with temporary.open("wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return target
