"""Staging validation for provider output artifacts."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


@dataclass(frozen=True)
class ArtifactRefV1:
    object_id: str
    sha256: str
    size_bytes: int
    media_type: str
    logical_path: str
    project_id: str


class ArtifactValidationError(ValueError):
    pass


class ArtifactPublisher:
    """Publish validated output from a private staging directory."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.staging = (self.root / ".staging").resolve()
        self.objects = (self.root / "objects").resolve()
        self.staging.mkdir(parents=True, exist_ok=True)
        self.objects.mkdir(parents=True, exist_ok=True)

    def publish(
        self,
        staging_file: Path,
        *,
        project_id: str,
        logical_path: str,
        media_type: str,
        expected_sha256: str,
        expected_size: int,
    ) -> ArtifactRefV1:
        source = staging_file.resolve()
        if not source.is_file() or not self._inside(source, self.staging):
            raise ArtifactValidationError("staging_file must be inside private staging")
        self._validate_logical_path(logical_path)
        actual_size = source.stat().st_size
        if actual_size != expected_size:
            raise ArtifactValidationError("artifact size does not match declaration")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        object_id = f"sha256:{digest}"
        if expected_sha256 != object_id:
            raise ArtifactValidationError("artifact hash does not match declaration")
        target = (self.objects / digest).resolve()
        if not self._inside(target, self.objects):
            raise ArtifactValidationError("object target escaped object root")
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        return ArtifactRefV1(
            object_id=object_id,
            sha256=object_id,
            size_bytes=actual_size,
            media_type=media_type,
            logical_path=logical_path,
            project_id=project_id,
        )

    @staticmethod
    def _inside(path: Path, root: Path) -> bool:
        try:
            path.relative_to(root)
        except ValueError:
            return False
        return True

    @staticmethod
    def _validate_logical_path(value: str) -> None:
        if not value or "\\" in value or "\x00" in value or value.startswith("/"):
            raise ArtifactValidationError("logical path is not portable")
        if ":" in value or any(part in {"", ".", ".."} for part in PurePosixPath(value).parts):
            raise ArtifactValidationError("logical path contains unsafe segments")
