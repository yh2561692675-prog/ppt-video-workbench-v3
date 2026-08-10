from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import UUID

from workbench_peripheral_adapter.client import PeripheralClientProtocol
from workbench_peripheral_adapter.dto import ArtifactDto


def materialize_artifact(
    adapter: PeripheralClientProtocol,
    *,
    job_id: UUID,
    artifact: ArtifactDto,
    project_dir: Path,
    destination_name: str | None = None,
) -> Path:
    project_dir = project_dir.resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    relative_destination = Path(destination_name or artifact.logical_name)
    if relative_destination.is_absolute() or ".." in relative_destination.parts:
        raise ValueError("artifact destination escapes project directory")
    destination = (project_dir / relative_destination).resolve()
    if not destination.is_relative_to(project_dir):
        raise ValueError("artifact destination escapes project directory")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.parent / f".s1-{job_id}-{artifact.artifact_id}.tmp"
    digest = hashlib.sha256()
    total = 0
    try:
        with temporary.open("wb") as stream:
            for chunk in adapter.stream_artifact(job_id, artifact.artifact_id):
                total += len(chunk)
                digest.update(chunk)
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        if total != artifact.size_bytes or digest.hexdigest() != artifact.sha256:
            raise ValueError("materialized artifact failed length or digest verification")
        temporary.replace(destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)
