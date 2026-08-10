from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

from peripheral_host.artifacts import sha256_file
from peripheral_host.errors import ArtifactIntegrityError
from peripheral_host.paths import lexical_workspace_path, resolve_workspace_path
from peripheral_host.repositories import ArtifactRecord
from peripheral_host.service import JobService

_CHUNK_SIZE = 1024 * 1024


def get_streamable_artifact(
    service: JobService,
    job_id: UUID,
    artifact_id: UUID,
) -> tuple[ArtifactRecord, Path]:
    records = service.list_artifacts(job_id)
    record = next((item for item in records if item.artifact_id == artifact_id), None)
    if record is None:
        raise ArtifactIntegrityError("artifact does not belong to the requested job")

    lexical = lexical_workspace_path(service.workspace_root, record.relative_path)
    if lexical.is_symlink():
        raise ArtifactIntegrityError("artifact must not be a symbolic link")
    path = resolve_workspace_path(service.workspace_root, record.relative_path)
    if not path.is_file():
        raise ArtifactIntegrityError("artifact must be an existing regular file")
    stat = path.stat()
    if stat.st_size != record.size_bytes or sha256_file(path) != record.sha256:
        raise ArtifactIntegrityError("artifact metadata does not match stored content")
    return record, path


def stream_verified_file(path: Path, record: ArtifactRecord) -> Iterator[bytes]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
            size += len(chunk)
            yield chunk
    stat = path.stat()
    if size != record.size_bytes or digest.hexdigest() != record.sha256 or stat.st_size != size:
        raise ArtifactIntegrityError("artifact changed during streaming")
