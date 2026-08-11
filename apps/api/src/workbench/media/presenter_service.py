from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from workbench.domain.models import ProjectManifest
from workbench.domain.presenter import PresentationMode, PresenterSource
from workbench.services.project_service import ProjectService

from .presenter_probe import PresenterMediaError, PresenterMediaInfo, probe_presenter

PresenterProbe = Callable[[Path], PresenterMediaInfo]


class PresenterImportService:
    def __init__(
        self,
        projects: ProjectService,
        probe: PresenterProbe | None = None,
    ) -> None:
        self.projects = projects
        self.probe = probe or probe_presenter

    def import_bytes(self, project_id: UUID, filename: str, content: bytes) -> ProjectManifest:
        suffix = Path(filename).suffix.lower()
        if suffix not in {".mp4", ".mov"}:
            raise PresenterMediaError(
                "PRESENTER_FILE_UNSUPPORTED", "only MP4 and MOV presenter sources are supported"
            )
        if not content:
            raise PresenterMediaError("PRESENTER_DECODE_FAILED", "presenter source is empty")
        current = self.projects.get(project_id)
        project_root = (self.projects.workspace_root / current.project_dir).resolve()
        source_root = project_root / "01_源文件" / "presenter"
        source_root.mkdir(parents=True, exist_ok=True)
        temporary = source_root / f".presenter-upload-{uuid4().hex}{suffix}.tmp"
        try:
            temporary.write_bytes(content)
            info = self.probe(temporary)
            destination = source_root / f"source-{info.sha256[:16]}{suffix}"
            if destination.exists():
                temporary.unlink()
            else:
                os.replace(temporary, destination)
            relative_path = destination.relative_to(project_root).as_posix()
            source = PresenterSource(
                id=uuid5(project_id, f"presenter:{info.sha256}"),
                relative_path=relative_path,
                sha256=info.sha256,
                duration_ms=info.duration_ms,
                media_type="video/quicktime" if suffix == ".mov" else "video/mp4",
                probe_snapshot=info.model_dump(mode="json", exclude={"path"}),
            )
            payload = current.model_dump(mode="python")
            payload.update(
                presentation_mode=PresentationMode.HUMAN_PRESENTER,
                presenter_source=source,
                presenter_timeline=None,
            )
            return self.projects.save(ProjectManifest.model_validate(payload))
        finally:
            temporary.unlink(missing_ok=True)
