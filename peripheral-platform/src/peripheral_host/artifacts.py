from __future__ import annotations

import hashlib
import os
import re
import shutil
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from peripheral_contracts import ArtifactRef

from peripheral_host.errors import ArtifactIntegrityError, ArtifactPublishError
from peripheral_host.paths import lexical_workspace_path, resolve_workspace_path

_LOGICAL_NAME = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_COPY_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class VerifiedArtifact:
    path: Path
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class PublishedArtifact:
    artifact_id: UUID
    job_id: UUID
    project_id: UUID
    path: Path
    relative_path: str
    logical_name: str
    kind: str
    version: int
    size_bytes: int
    sha256: str


def sha256_file(path: Path, chunk_size: int = _COPY_CHUNK_SIZE) -> str:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def verify_artifact(ref: ArtifactRef, root: Path) -> VerifiedArtifact:
    target = resolve_workspace_path(root, ref.path)
    lexical_target = lexical_workspace_path(root, ref.path)
    if lexical_target.is_symlink():
        raise ArtifactIntegrityError("artifact must not be a symbolic link")
    if not target.is_file():
        raise ArtifactIntegrityError("artifact must be an existing regular file")

    before = target.stat()
    if before.st_size != ref.size_bytes:
        raise ArtifactIntegrityError("artifact size does not match reference")
    actual_sha256 = sha256_file(target)
    after = target.stat()
    before_identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_identity = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if after_identity != before_identity:
        raise ArtifactIntegrityError("artifact changed during verification")
    if actual_sha256 != ref.sha256:
        raise ArtifactIntegrityError("artifact sha256 does not match reference")
    return VerifiedArtifact(path=target, size_bytes=after.st_size, sha256=actual_sha256)


def publish_output(
    *,
    workspace_root: Path,
    attempt_root: Path,
    staged_path: Path,
    project_id: UUID,
    job_id: UUID,
    logical_name: str,
    kind: str,
    version: int,
) -> PublishedArtifact:
    workspace = workspace_root.resolve()
    attempt = attempt_root.resolve(strict=False)
    if attempt == workspace or not attempt.is_relative_to(workspace):
        raise ArtifactPublishError("attempt directory must be inside workspace")
    if attempt_root.is_symlink() or staged_path.is_symlink():
        raise ArtifactPublishError("attempt output must not be a symbolic link")

    staged = staged_path.resolve(strict=False)
    if staged == attempt or not staged.is_relative_to(attempt):
        raise ArtifactPublishError("staged file must be inside current attempt directory")
    if not staged.is_file():
        raise ArtifactPublishError("staged output must be an existing regular file")
    if not _LOGICAL_NAME.fullmatch(logical_name):
        raise ArtifactPublishError("logical artifact name is invalid")
    if not kind or len(kind) > 64:
        raise ArtifactPublishError("artifact kind is invalid")
    if version < 1:
        raise ArtifactPublishError("artifact version must be positive")

    relative_target = (
        Path("projects")
        / str(project_id)
        / "state"
        / "artifacts"
        / logical_name
        / f"v{version:04d}"
        / staged.name
    )
    target = resolve_workspace_path(workspace, relative_target.as_posix())
    version_root = target.parent
    try:
        version_root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise ArtifactPublishError("artifact version already exists") from error

    temporary = version_root / f".{staged.name}.{uuid4().hex}.tmp"
    try:
        with staged.open("rb") as source, temporary.open("xb") as destination:
            shutil.copyfileobj(source, destination, length=_COPY_CHUNK_SIZE)
            destination.flush()
            os.fsync(destination.fileno())
        size_bytes = temporary.stat().st_size
        digest = sha256_file(temporary)
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        with suppress(OSError):
            version_root.rmdir()
        raise

    return PublishedArtifact(
        artifact_id=uuid4(),
        job_id=job_id,
        project_id=project_id,
        path=target,
        relative_path=target.relative_to(workspace).as_posix(),
        logical_name=logical_name,
        kind=kind,
        version=version,
        size_bytes=size_bytes,
        sha256=digest,
    )
