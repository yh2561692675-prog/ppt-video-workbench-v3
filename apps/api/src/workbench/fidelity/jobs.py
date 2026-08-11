from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from .models import FidelityJobRecord, FidelityJobRequest, SlideFidelityPage
from .scanner import FidelityScanError, PptxFidelityScanner


class FidelityJobService:
    def __init__(
        self,
        root: Path,
        scanner: PptxFidelityScanner | None = None,
        project_dir_resolver: Callable[[UUID], str] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.scanner = scanner or PptxFidelityScanner()
        self.project_dir_resolver = project_dir_resolver
        self._jobs: dict[UUID, FidelityJobRecord] = {}
        self._lock = RLock()

    def submit(self, project_id: UUID, request: FidelityJobRequest) -> FidelityJobRecord:
        job_id = uuid4()
        record = FidelityJobRecord(job_id=job_id, status="running")
        with self._lock:
            self._jobs[job_id] = record
        try:
            pptx_path = self._safe_path(project_id, request.pptx_path)
            output_dir = self._safe_path(project_id, request.output_dir)
            manifest = self.scanner.scan(pptx_path, output_dir, request.policy)
            degraded = any(
                page.downgrade_reason is not None or any(issue.blocking for issue in page.issues)
                for page in manifest.pages
            )
            record = record.model_copy(
                update={"status": "degraded" if degraded else "succeeded", "manifest": manifest}
            )
        except FidelityScanError as error:
            record = record.model_copy(
                update={"status": "failed", "error_code": error.code, "error": str(error)}
            )
        except Exception as error:  # noqa: BLE001 - persist job boundary failures
            record = record.model_copy(
                update={
                    "status": "failed",
                    "error_code": "fidelity_scan_failed",
                    "error": str(error),
                }
            )
        with self._lock:
            self._jobs[job_id] = record
        return record

    def get(self, project_id: UUID, job_id: UUID) -> FidelityJobRecord:
        with self._lock:
            record = self._jobs.get(job_id)
        if record is None:
            raise KeyError(job_id)
        if record.manifest and not Path(record.manifest.source_path).is_relative_to(
            self._safe_base(project_id)
        ):
            raise KeyError(job_id)
        return record

    def pages(self, project_id: UUID, job_id: UUID | None = None) -> list[SlideFidelityPage]:
        if job_id is not None:
            record = self.get(project_id, job_id)
        else:
            with self._lock:
                candidates = [item for item in self._jobs.values() if item.manifest is not None]
            if not candidates:
                raise KeyError(project_id)
            record = candidates[-1]
        if record.manifest is None:
            raise KeyError(project_id)
        return record.manifest.pages

    def _safe_path(self, project_id: UUID, relative: str) -> Path:
        base = self._safe_base(project_id)
        candidate = (base / relative).resolve()
        try:
            candidate.relative_to(base)
        except ValueError as error:
            raise FidelityScanError(
                "fidelity_path_outside_project", "高保真路径必须位于项目目录内"
            ) from error
        return candidate

    def _safe_base(self, project_id: UUID) -> Path:
        base = (
            (self.root / self.project_dir_resolver(project_id)).resolve()
            if self.project_dir_resolver is not None
            else (self.root / str(project_id)).resolve()
        )
        base.mkdir(parents=True, exist_ok=True)
        return base
