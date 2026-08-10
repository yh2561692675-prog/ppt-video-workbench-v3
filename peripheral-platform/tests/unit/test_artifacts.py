from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
from peripheral_contracts import ArtifactRef
from peripheral_host.artifacts import publish_output, sha256_file, verify_artifact
from peripheral_host.errors import ArtifactIntegrityError, ArtifactPublishError


def _artifact_ref(path: str, payload: bytes) -> ArtifactRef:
    return ArtifactRef(
        artifact_id=uuid4(),
        kind="source",
        path=path,
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def test_verify_artifact_accepts_matching_regular_file(tmp_path: Path):
    payload = b"verified input"
    artifact_ref = _artifact_ref("projects/demo/input.txt", payload)
    target = tmp_path / artifact_ref.path
    target.parent.mkdir(parents=True)
    target.write_bytes(payload)

    verified = verify_artifact(artifact_ref, tmp_path)

    assert verified.path == target.resolve()
    assert verified.size_bytes == len(payload)
    assert verified.sha256 == hashlib.sha256(payload).hexdigest()


def test_verify_artifact_rejects_hash_mismatch(tmp_path: Path):
    artifact_ref = _artifact_ref("projects/demo/input.txt", b"original")
    target = tmp_path / artifact_ref.path
    target.parent.mkdir(parents=True)
    target.write_bytes(b"changed!")

    with pytest.raises(ArtifactIntegrityError, match="sha256"):
        verify_artifact(artifact_ref, tmp_path)


def test_verify_artifact_rejects_symbolic_link(tmp_path: Path):
    payload = b"linked input"
    source = tmp_path / "source.txt"
    source.write_bytes(payload)
    link = tmp_path / "projects" / "demo" / "input.txt"
    link.parent.mkdir(parents=True)
    try:
        link.symlink_to(source)
    except OSError as error:
        if error.winerror == 1314:
            pytest.skip("symbolic links require Windows Developer Mode or elevated permission")
        raise

    with pytest.raises(ArtifactIntegrityError, match="symbolic link"):
        verify_artifact(_artifact_ref("projects/demo/input.txt", payload), tmp_path)


def test_sha256_file_streams_in_chunks(tmp_path: Path):
    payload = b"0123456789" * 1024
    target = tmp_path / "large.bin"
    target.write_bytes(payload)

    assert sha256_file(target, chunk_size=7) == hashlib.sha256(payload).hexdigest()


def test_publish_output_atomically_creates_versioned_artifact(tmp_path: Path):
    project_id = uuid4()
    job_id = uuid4()
    attempt_root = tmp_path / "workspace-data" / "attempts" / "attempt-1"
    attempt_root.mkdir(parents=True)
    staged_path = attempt_root / "echo.txt"
    staged_path.write_bytes(b"echo output")

    published = publish_output(
        workspace_root=tmp_path,
        attempt_root=attempt_root,
        staged_path=staged_path,
        project_id=project_id,
        job_id=job_id,
        logical_name="echo-text",
        kind="text",
        version=1,
    )

    expected = (
        tmp_path
        / "projects"
        / str(project_id)
        / "state"
        / "artifacts"
        / "echo-text"
        / "v0001"
        / "echo.txt"
    )
    assert published.path == expected.resolve()
    assert published.job_id == job_id
    assert published.project_id == project_id
    assert published.relative_path == expected.relative_to(tmp_path).as_posix()
    assert published.size_bytes == len(b"echo output")
    assert expected.read_bytes() == b"echo output"


def test_publish_output_rejects_staged_file_outside_attempt(tmp_path: Path):
    attempt_root = tmp_path / "workspace-data" / "attempts" / "attempt-1"
    attempt_root.mkdir(parents=True)
    staged_path = tmp_path / "outside.txt"
    staged_path.write_text("outside", encoding="utf-8")

    with pytest.raises(ArtifactPublishError, match="attempt"):
        publish_output(
            workspace_root=tmp_path,
            attempt_root=attempt_root,
            staged_path=staged_path,
            project_id=uuid4(),
            job_id=uuid4(),
            logical_name="echo-text",
            kind="text",
            version=1,
        )


def test_publish_output_rejects_existing_version_directory(tmp_path: Path):
    project_id = uuid4()
    attempt_root = tmp_path / "workspace-data" / "attempts" / "attempt-1"
    attempt_root.mkdir(parents=True)
    staged_path = attempt_root / "echo.txt"
    staged_path.write_text("new", encoding="utf-8")
    version_root = (
        tmp_path
        / "projects"
        / str(project_id)
        / "state"
        / "artifacts"
        / "echo-text"
        / "v0001"
    )
    version_root.mkdir(parents=True)

    with pytest.raises(ArtifactPublishError, match="already exists"):
        publish_output(
            workspace_root=tmp_path,
            attempt_root=attempt_root,
            staged_path=staged_path,
            project_id=project_id,
            job_id=uuid4(),
            logical_name="echo-text",
            kind="text",
            version=1,
        )
