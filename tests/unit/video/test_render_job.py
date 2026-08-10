from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from workbench.domain.enums import JobStatus
from workbench.jobs.repository import JobRepository
from workbench.storage.workspace_db import WorkspaceDatabase
from workbench.video.errors import RenderPageFailed
from workbench.video.render_job import RenderJobService


class FakePreflight:
    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.props = type("Props", (), {"model_dump": lambda self, mode=None: {"pages": []}})()


class FakePreview:
    def preflight(self, project_id):
        return FakePreflight()


class FakeProjects:
    workspace_root = Path(".").resolve()

    def __init__(self, root: Path) -> None:
        self.workspace_root = root
        self.saved = []

    def get(self, project_id):
        return type("Project", (), {"id": project_id, "project_dir": "project", "audit_log": []})()

    def save(self, project):
        self.saved.append(project)
        return project


def _repo(tmp_path: Path) -> JobRepository:
    database = WorkspaceDatabase(tmp_path / "workspace.db")
    database.initialize()
    return JobRepository(database)


def test_submit_same_input_twice_returns_one_active_job(tmp_path: Path) -> None:
    project_id = uuid4()
    service = RenderJobService(
        FakeProjects(tmp_path),
        FakePreview(),
        object(),
        repository=_repo(tmp_path),
    )

    first = service.submit(project_id)
    second = service.submit(project_id)

    assert first.created is True
    assert second.created is False
    assert second.job.id == first.job.id


def test_handler_maps_known_failure_and_persists_safe_code(tmp_path: Path) -> None:
    project_id = uuid4()

    class FailingExporter:
        def export(self, project_id, *, context):
            raise RenderPageFailed("renderer credential=value")

    repository = _repo(tmp_path)
    service = RenderJobService(
        FakeProjects(tmp_path),
        FakePreview(),
        FailingExporter(),
        repository=repository,
    )
    job = service.submit(project_id).job
    service.handle(job)
    failed = repository.get(job.id)
    assert failed.status is JobStatus.FAILED
    assert failed.error_code == "render_page_failed"
    assert "credential=value" not in (failed.error or "")


def test_succeeded_job_is_reused_only_after_published_artifacts_verify(tmp_path: Path) -> None:
    project_id = uuid4()
    repository = _repo(tmp_path)
    service = RenderJobService(
        FakeProjects(tmp_path), FakePreview(), object(), repository=repository
    )
    first = service.submit(project_id).job
    root = tmp_path / "project"
    package = root / "08_输出" / "制作包-job-1"
    package.mkdir(parents=True)
    artifact = package / "artifact.txt"
    artifact.write_bytes(b"verified")
    (package / "制作包清单.json").write_text(
        json.dumps(
            {
                "version": 1,
                "artifacts": [
                    {
                        "relative_path": "artifact.txt",
                        "size": artifact.stat().st_size,
                        "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    mp4 = root / "08_输出" / "最终视频.mp4"
    mp4.write_bytes(b"video")
    repository.mark_running(first.id)
    repository.succeed(
        first.id,
        {
            "mp4_relative_path": "08_输出/最终视频.mp4",
            "package_relative_path": "08_输出/制作包-job-1",
        },
    )

    reused = service.submit(project_id)
    assert reused.created is False
    assert reused.job.id == first.id

    artifact.write_bytes(b"tampered")
    replacement = service.submit(project_id)
    assert replacement.created is True
    assert replacement.job.id != first.id
    assert replacement.job.parent_job_id is None
