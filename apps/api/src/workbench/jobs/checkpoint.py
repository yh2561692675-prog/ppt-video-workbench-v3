from __future__ import annotations

import hashlib
import os
import re
import shutil
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from workbench.domain.enums import JobType


class CheckpointArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relative_path: str
    sha256: str = Field(min_length=64, max_length=64)
    size: int = Field(ge=0)


class Checkpoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID
    sequence: int = Field(ge=1)
    progress: float = Field(ge=0.0, le=1.0)
    stage: str
    payload: dict[str, Any] = Field(default_factory=dict)
    cache_keys: list[str] = Field(default_factory=list)
    artifacts: list[CheckpointArtifact] = Field(default_factory=list)
    temporary_paths: list[str] = Field(default_factory=list)
    remote_task_ids: list[str] = Field(default_factory=list)
    completed_stages: list[str] = Field(default_factory=list)
    preserve_manual_locks: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CheckpointStore:
    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir.resolve()
        self.directory = self.project_dir / "09_日志" / "检查点"

    def write(self, checkpoint: Checkpoint) -> Checkpoint:
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.path_for(checkpoint.job_id, checkpoint.sequence)
        if target.exists():
            raise FileExistsError(f"checkpoint sequence already exists: {checkpoint.sequence}")
        temporary = target.with_name(f".{target.name}.tmp")
        data = checkpoint.model_dump_json(indent=2)
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(data)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        return checkpoint

    def path_for(self, job_id: UUID, sequence: int) -> Path:
        return self.directory / f"{job_id}-{sequence:06d}.json"

    def checksum(self, checkpoint: Checkpoint) -> str:
        path = self.path_for(checkpoint.job_id, checkpoint.sequence)
        return _sha256(path)

    def next_sequence(self, job_id: UUID) -> int:
        sequences = [
            int(match.group(1))
            for path in self.directory.glob(f"{job_id}-*.json")
            if (match := re.fullmatch(rf"{re.escape(str(job_id))}-(\d{{6}})\.json", path.name))
        ]
        return max(sequences, default=0) + 1

    def latest(self, job_id: UUID) -> Checkpoint | None:
        candidates = sorted(
            self.directory.glob(f"{job_id}-*.json"),
            key=lambda path: path.name,
            reverse=True,
        )
        for path in candidates:
            try:
                return Checkpoint.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
        return None

    def restore(self, job_id: UUID, verify: bool = True) -> Checkpoint | None:
        for checkpoint in self.valid_checkpoints(job_id, verify=verify):
            return checkpoint
        return None

    def valid_checkpoints(self, job_id: UUID, *, verify: bool = True) -> Iterable[Checkpoint]:
        candidates = sorted(
            self.directory.glob(f"{job_id}-*.json"),
            key=lambda path: path.name,
            reverse=True,
        )
        for path in candidates:
            try:
                checkpoint = Checkpoint.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if checkpoint.job_id != job_id:
                continue
            if verify and not self._artifacts_valid(checkpoint):
                continue
            yield checkpoint

    def cleanup_temporary_paths(self, job_id: UUID) -> None:
        checkpoint = self.latest(job_id)
        if checkpoint is None:
            return
        for relative_path in checkpoint.temporary_paths:
            target = self._safe_path(relative_path)
            if target is None or target == self.project_dir:
                raise ValueError("checkpoint temporary path is outside the project")
            if target.is_symlink() or target.is_file():
                target.unlink(missing_ok=True)
            elif target.is_dir():
                shutil.rmtree(target)

    def _artifacts_valid(self, checkpoint: Checkpoint) -> bool:
        for artifact in checkpoint.artifacts:
            path = self._safe_path(artifact.relative_path)
            if path is None or not path.is_file():
                return False
            if path.stat().st_size != artifact.size or _sha256(path) != artifact.sha256:
                return False
        return True

    def _safe_path(self, relative_path: str) -> Path | None:
        candidate = (self.project_dir / relative_path).resolve()
        if self.project_dir not in candidate.parents:
            return None
        return candidate


class JobContext:
    def __init__(
        self,
        job_id: UUID,
        project_dir: Path,
        job_type: JobType,
        *,
        paid: bool = False,
        checkpoint_store: CheckpointStore | None = None,
        remote_status_lookup: Callable[[str], str | None] | None = None,
    ) -> None:
        self.job_id = job_id
        self.project_dir = project_dir.resolve()
        self.job_type = job_type
        self.paid = paid
        self.store = checkpoint_store or CheckpointStore(self.project_dir)
        self.remote_status_lookup = remote_status_lookup
        self._pause = False
        self._cancel = False
        self._remote_status_results: dict[str, str | None] = {}

    def checkpoint(
        self,
        progress: float,
        payload: Mapping[str, Any],
        artifacts: Iterable[Path] = (),
    ) -> Checkpoint:
        if not 0.0 <= progress <= 1.0:
            raise ValueError("checkpoint progress must be between zero and one")
        artifact_records = [_artifact(self.project_dir, path) for path in artifacts]
        sanitized = _sanitize(dict(payload))
        if not isinstance(sanitized, dict):
            raise ValueError("checkpoint payload must be an object")
        checkpoint = Checkpoint(
            job_id=self.job_id,
            sequence=self.store.next_sequence(self.job_id),
            progress=progress,
            stage=str(sanitized.get("stage", self.job_type.value)),
            payload=sanitized,
            cache_keys=_string_list(sanitized.get("cache_keys", [])),
            artifacts=artifact_records,
            temporary_paths=_safe_relative_list(
                self.project_dir, sanitized.get("temporary_paths", [])
            ),
            remote_task_ids=_string_list(sanitized.get("remote_task_ids", [])),
            completed_stages=_string_list(sanitized.get("completed_stages", [])),
            preserve_manual_locks=bool(sanitized.get("preserve_manual_locks", False)),
        )
        return self.store.write(checkpoint)

    def request_pause(self) -> None:
        self._pause = True

    def request_cancel(self) -> None:
        self._cancel = True
        checkpoint = self.store.latest(self.job_id)
        if checkpoint is not None:
            for relative_path in checkpoint.temporary_paths:
                path = self.store._safe_path(relative_path)
                if path is not None:
                    path.unlink(missing_ok=True)

    @property
    def should_pause(self) -> bool:
        return self._pause

    @property
    def should_cancel(self) -> bool:
        return self._cancel

    def restore(self, verify: bool = True) -> Checkpoint | None:
        return self.store.restore(self.job_id, verify=verify)

    @property
    def remote_status_results(self) -> dict[str, str | None]:
        return dict(self._remote_status_results)

    def query_remote_tasks(self, checkpoint: Checkpoint | None = None) -> None:
        if not self.paid or self.remote_status_lookup is None:
            return
        current = checkpoint or self.restore()
        if current is None:
            return
        for remote_id in current.remote_task_ids:
            self._remote_status_results[remote_id] = self.remote_status_lookup(remote_id)


def _artifact(project_dir: Path, path: Path) -> CheckpointArtifact:
    target = path.resolve()
    if project_dir not in target.parents or not target.is_file():
        raise ValueError(f"checkpoint artifact must be an existing project file: {path}")
    return CheckpointArtifact(
        relative_path=target.relative_to(project_dir).as_posix(),
        sha256=_sha256(target),
        size=target.stat().st_size,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_SECRET_KEY = re.compile(r"(token|secret|password|credential|authorization|api[-_]?key)", re.I)


def _sanitize(value: Any, *, key: str = "") -> Any:
    if key and _SECRET_KEY.search(key):
        return "<redacted>"
    if isinstance(value, Mapping):
        return {
            str(item_key): _sanitize(item, key=str(item_key)) for item_key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    if isinstance(value, (UUID, Path)):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("checkpoint list fields must be lists")
    return [str(item) for item in value]


def _safe_relative_list(project_dir: Path, value: Any) -> list[str]:
    paths = _string_list(value)
    result: list[str] = []
    for relative_path in paths:
        candidate = (project_dir / relative_path).resolve()
        if project_dir not in candidate.parents:
            raise ValueError("checkpoint temporary path escapes project directory")
        result.append(candidate.relative_to(project_dir).as_posix())
    return result
