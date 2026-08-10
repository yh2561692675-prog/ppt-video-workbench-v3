from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from workbench.domain.errors import ManifestRecoveryError, ProjectPathViolation
from workbench.domain.models import ProjectManifest


class ManifestStore:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()

    def load(self, project_dir: Path) -> ProjectManifest:
        safe_dir = self._safe_project_dir(project_dir)
        return self._read(safe_dir / "project.json")

    def save(self, project_dir: Path, manifest: ProjectManifest) -> None:
        safe_dir = self._safe_project_dir(project_dir)
        manifest_path = safe_dir / "project.json"
        backup_path = safe_dir / "project.json.bak"
        temp_path = safe_dir / f".project.json.{uuid4().hex}.tmp"
        backup_temp = safe_dir / f".project.json.bak.{uuid4().hex}.tmp"

        self._write_synced(temp_path, manifest.model_dump_json(indent=2))
        try:
            if manifest_path.exists():
                self._copy_synced(manifest_path, backup_temp)
                os.replace(backup_temp, backup_path)
            os.replace(temp_path, manifest_path)
            self._sync_directory(safe_dir)
        finally:
            temp_path.unlink(missing_ok=True)
            backup_temp.unlink(missing_ok=True)

    def recover(self, project_dir: Path) -> ProjectManifest:
        safe_dir = self._safe_project_dir(project_dir)
        try:
            return self._read(safe_dir / "project.json")
        except (OSError, ValidationError):
            backup_path = safe_dir / "project.json.bak"
            try:
                recovered = self._read(backup_path)
            except (OSError, ValidationError) as error:
                message = "Neither project.json nor its backup is valid"
                raise ManifestRecoveryError(message) from error

            restore_temp = safe_dir / f".project.json.restore.{uuid4().hex}.tmp"
            self._copy_synced(backup_path, restore_temp)
            try:
                os.replace(restore_temp, safe_dir / "project.json")
                self._sync_directory(safe_dir)
            finally:
                restore_temp.unlink(missing_ok=True)
            return recovered

    def _safe_project_dir(self, project_dir: Path) -> Path:
        resolved = project_dir.resolve()
        if not resolved.is_relative_to(self.workspace_root) or resolved == self.workspace_root:
            raise ProjectPathViolation(f"Project path is outside workspace: {project_dir}")
        if not resolved.is_dir():
            raise ProjectPathViolation(f"Project directory does not exist: {project_dir}")
        return resolved

    @staticmethod
    def _read(path: Path) -> ProjectManifest:
        return ProjectManifest.model_validate_json(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_synced(path: Path, text: str) -> None:
        with path.open("w", encoding="utf-8", newline="\n") as destination:
            destination.write(text)
            destination.write("\n")
            destination.flush()
            os.fsync(destination.fileno())

    @staticmethod
    def _copy_synced(source: Path, destination: Path) -> None:
        with source.open("rb") as source_file, destination.open("wb") as destination_file:
            shutil.copyfileobj(source_file, destination_file)
            destination_file.flush()
            os.fsync(destination_file.fileno())

    @staticmethod
    def _sync_directory(directory: Path) -> None:
        if os.name == "nt":
            return
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
