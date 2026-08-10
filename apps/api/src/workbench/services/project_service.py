from __future__ import annotations

import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import delete, insert, select, update

from workbench.domain.enums import NodeStatus
from workbench.domain.models import ProjectManifest
from workbench.jobs.repository import JobRepository
from workbench.storage.manifest_store import ManifestStore
from workbench.storage.project_paths import (
    MAPPED_PROJECT_FOLDERS,
    ProjectStorageRoots,
    create_project_storage_links,
)
from workbench.storage.workspace_db import WorkspaceDatabase, dispose_database, projects

PROJECT_FOLDERS = (
    "01_源文件",
    "02_页面预览",
    "03_文字识别",
    "04_旁白",
    "05_音频",
    "06_字幕",
    "07_视频工程",
    "08_输出",
    "09_日志",
)
WINDOWS_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class ProjectService:
    def __init__(
        self,
        workspace_root: Path,
        *,
        storage_roots: ProjectStorageRoots | None = None,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self.storage_roots = storage_roots or ProjectStorageRoots()
        self.storage_roots.validate()
        self.database = WorkspaceDatabase(self.workspace_root / "workspace.db")
        self.database.initialize()
        self.store = ManifestStore(self.workspace_root)
        self.jobs = JobRepository(self.database)
        self.jobs.recover_interrupted_jobs()
        self.rebuild_index()

    def create(self, name: str) -> ProjectManifest:
        safe_name = _safe_project_name(name)
        timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M")
        base_name = f"{safe_name}_{timestamp}"
        project_dir = self._available_project_dir(base_name)
        project_dir.mkdir()
        for folder in PROJECT_FOLDERS:
            if self.storage_roots.enabled and folder in MAPPED_PROJECT_FOLDERS:
                continue
            (project_dir / folder).mkdir()

        try:
            create_project_storage_links(project_dir, project_dir.name, self.storage_roots)
        except Exception:
            shutil.rmtree(project_dir, ignore_errors=True)
            raise

        now = datetime.now(UTC)
        manifest = ProjectManifest(
            id=uuid4(),
            name=name.strip(),
            project_dir=project_dir.name,
            created_at=now,
            updated_at=now,
            current_step=1,
            status=NodeStatus.NOT_STARTED,
        )
        self.store.save(project_dir, manifest)
        self._upsert_index(manifest)
        return manifest

    def list(self) -> list[ProjectManifest]:
        with self.database.connect() as connection:
            rows = connection.execute(
                select(projects.c.project_dir).order_by(projects.c.updated_at.desc())
            ).all()
        manifests = []
        for (project_dir,) in rows:
            try:
                manifests.append(self.store.recover(self.workspace_root / project_dir))
            except OSError:
                continue
        return manifests

    def get(self, project_id: UUID) -> ProjectManifest:
        with self.database.connect() as connection:
            project_dir = connection.execute(
                select(projects.c.project_dir).where(projects.c.id == str(project_id))
            ).scalar_one_or_none()
        if project_dir is None:
            raise KeyError(project_id)
        return self.store.recover(self.workspace_root / project_dir)

    def set_step(self, project_id: UUID, step: int) -> ProjectManifest:
        if not 1 <= step <= 7:
            raise ValueError("step must be between 1 and 7")
        return self._change(project_id, current_step=step)

    def pause(self, project_id: UUID) -> ProjectManifest:
        return self._change(project_id, status=NodeStatus.PAUSED)

    def resume(self, project_id: UUID) -> ProjectManifest:
        return self._change(project_id, status=NodeStatus.NOT_STARTED)

    def disk_status(self) -> dict[str, int]:
        usage = shutil.disk_usage(self.workspace_root)
        return {"total": usage.total, "used": usage.used, "free": usage.free}

    def rebuild_index(self) -> int:
        discovered: list[ProjectManifest] = []
        for manifest_path in self.workspace_root.glob("*/project.json"):
            try:
                discovered.append(self.store.recover(manifest_path.parent))
            except Exception:
                continue
        with self.database.engine.begin() as connection:
            connection.execute(delete(projects))
        for manifest in discovered:
            self._upsert_index(manifest)
        return len(discovered)

    def close(self) -> None:
        dispose_database(self.database)

    def save(self, manifest: ProjectManifest) -> ProjectManifest:
        updated = manifest.model_copy(update={"updated_at": datetime.now(UTC)})
        self.store.save(self.workspace_root / updated.project_dir, updated)
        self._upsert_index(updated)
        return updated

    def _change(self, project_id: UUID, **changes: object) -> ProjectManifest:
        current = self.get(project_id)
        updated = current.model_copy(update={**changes, "updated_at": datetime.now(UTC)})
        self.store.save(self.workspace_root / current.project_dir, updated)
        self._upsert_index(updated)
        return updated

    def _upsert_index(self, manifest: ProjectManifest) -> None:
        values = {
            "id": str(manifest.id),
            "name": manifest.name,
            "project_dir": manifest.project_dir,
            "manifest_path": str(Path(manifest.project_dir) / "project.json"),
            "current_step": manifest.current_step,
            "status": manifest.status.value,
            "updated_at": manifest.updated_at.isoformat(),
        }
        with self.database.engine.begin() as connection:
            exists = connection.execute(
                select(projects.c.id).where(projects.c.id == str(manifest.id))
            ).scalar_one_or_none()
            if exists is None:
                connection.execute(insert(projects).values(**values))
            else:
                connection.execute(
                    update(projects).where(projects.c.id == str(manifest.id)).values(**values)
                )

    def _available_project_dir(self, base_name: str) -> Path:
        candidate = self.workspace_root / base_name
        suffix = 2
        while candidate.exists():
            candidate = self.workspace_root / f"{base_name}_{suffix}"
            suffix += 1
        return candidate


def _safe_project_name(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        raise ValueError("project name is required")
    safe = WINDOWS_INVALID.sub("_", stripped).rstrip(". ")
    if not safe:
        raise ValueError("project name does not contain usable characters")
    if safe.upper() in WINDOWS_RESERVED:
        safe = f"_{safe}"
    return safe[:80]
