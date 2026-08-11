from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from workbench.domain.enums import JobStatus
from workbench.jobs.repository import JobRepository
from workbench.rendering.feature_flags import RenderFeatureFlags
from workbench.rendering.hashing import sha256_json
from workbench.rendering.models import GraphCanvas, RenderGraphV2
from workbench.storage.workspace_db import WorkspaceDatabase
from workbench.video.render_job import RenderJobService


class FakePreflight:
    allowed = True
    props = type("Props", (), {"model_dump": lambda self, mode=None: {"pages": []}})()


class FakePreview:
    def preflight(self, project_id):
        return FakePreflight()


class FakeProjects:
    def __init__(self, root: Path) -> None:
        self.workspace_root = root

    def get(self, project_id):
        return type("Project", (), {"id": project_id, "project_dir": "project", "audit_log": []})()

    def save(self, project):
        return project


def _repo(tmp_path: Path) -> JobRepository:
    database = WorkspaceDatabase(tmp_path / "workspace.db")
    database.initialize()
    return JobRepository(database)


def test_v2_job_pins_graph_snapshot_and_worker_uses_pinned_graph(tmp_path: Path) -> None:
    project_id = uuid4()
    graph = RenderGraphV2(
        project_id=project_id,
        timeline_revision=4,
        duration_us=1_000_000,
        canvas=GraphCanvas(width=1920, height=1080, fps=30),
        graph_hash="0" * 64,
    )
    graph = graph.model_copy(
        update={
            "graph_hash": sha256_json(
                graph.model_dump(mode="json", exclude={"graph_hash", "created_at"})
            )
        }
    )
    seen: list[str] = []

    def export_v2(_, received, __):
        seen.append(received.graph_hash)
        return {
            "mp4_relative_path": "08_输出/最终视频.mp4",
            "package_relative_path": "08_输出/制作包",
        }

    service = RenderJobService(
        FakeProjects(tmp_path),
        FakePreview(),
        object(),
        repository=_repo(tmp_path),
        graph_provider=lambda _: graph,
        graph_exporter=export_v2,
        feature_flags=RenderFeatureFlags(export=True, compile=True, renderer_generation="v2"),
    )
    job = service.submit(project_id).job
    assert job.payload["render_generation"] == "v2"
    assert job.payload["graph_id"] == str(graph.graph_id)
    assert job.payload["graph_hash"] == graph.graph_hash
    service.handle(job)
    assert seen == [graph.graph_hash]
    assert service.repository.get(job.id).status is JobStatus.SUCCEEDED


def test_v2_export_flag_does_not_override_v1_generation(tmp_path: Path) -> None:
    project_id = uuid4()
    service = RenderJobService(
        FakeProjects(tmp_path),
        FakePreview(),
        object(),
        repository=_repo(tmp_path),
        graph_provider=lambda _: (_ for _ in ()).throw(AssertionError("V2 must not be used")),
        feature_flags=RenderFeatureFlags(export=True, renderer_generation="v1"),
    )
    submission = service.submit(project_id)
    assert submission.created
    assert submission.job.payload == {"props": {"pages": []}}
