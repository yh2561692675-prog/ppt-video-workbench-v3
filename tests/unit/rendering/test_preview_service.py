from __future__ import annotations

from pathlib import Path
from uuid import UUID

from workbench.domain.enums import JobStatus, JobType
from workbench.jobs.execution import PersistentRenderExecutionContext
from workbench.media.probe import MediaProbeResult, MediaStreamProbe
from workbench.rendering.hashing import sha256_json
from workbench.rendering.models import GraphCanvas, RenderGraphV2
from workbench.rendering.preview_service import (
    AuthoritativePreviewJobRequest,
    AuthoritativePreviewService,
)
from workbench.rendering.snapshot_store import RenderGraphSnapshotStore
from workbench.services.project_service import ProjectService


def _graph(project_id: UUID) -> RenderGraphV2:
    draft = RenderGraphV2(
        project_id=project_id,
        timeline_revision=1,
        duration_us=3_000_000,
        canvas=GraphCanvas(width=1920, height=1080, fps=30, duration_us=3_000_000),
        graph_hash="0" * 64,
    )
    payload = draft.model_dump(mode="json", exclude={"graph_hash", "created_at"})
    return draft.model_copy(update={"graph_hash": sha256_json(payload)})


def _valid_probe(_: Path) -> MediaProbeResult:
    return MediaProbeResult(
        container="mov,mp4",
        duration_us=1_000_000,
        tool_version="ffprobe test",
        streams=[
            MediaStreamProbe(
                index=0,
                kind="video",
                codec="h264",
                width=1920,
                height=1080,
                fps_num=30,
                fps_den=1,
            ),
            MediaStreamProbe(index=1, kind="audio", codec="aac"),
        ],
    )


def test_preview_service_freezes_snapshot_projects_and_publishes(tmp_path: Path) -> None:
    projects = ProjectService(tmp_path)
    project = projects.create("preview")
    root = tmp_path / project.project_dir
    graph = _graph(project.id)
    RenderGraphSnapshotStore(root).set_current(project.id, graph)

    def execute(
        projected: RenderGraphV2,
        output_dir: Path,
        context: PersistentRenderExecutionContext,
    ) -> Path:
        assert projected.duration_us == 1_000_000
        output_dir.mkdir(parents=True)
        video = output_dir / "preview.mp4"
        video.write_bytes(b"preview-video")
        return video

    service = AuthoritativePreviewService(
        projects, executor=execute, artifact_probe=_valid_probe
    )
    job = service.submit(
        project.id,
        AuthoritativePreviewJobRequest(
            graph_id=graph.graph_id,
            graph_hash=graph.graph_hash,
            start_us=1_000_000,
            end_us=2_000_000,
        ),
    )
    claimed = projects.jobs.claim_next(JobType.RENDER_PREVIEW)
    assert claimed is not None
    service.handle(claimed)

    completed = projects.jobs.get(job.id)
    assert completed.status is JobStatus.SUCCEEDED
    assert completed.result is not None
    manifest = completed.result["manifest"]
    assert manifest["graph_hash"] == graph.graph_hash
    assert manifest["start_us"] == 1_000_000
    assert manifest["duration_us"] == 1_000_000
    assert manifest["runtime_version"] == "rendergraph-v2"
    assert manifest["has_audio"] is True
    assert (root / manifest["video_relative_path"]).read_bytes() == b"preview-video"
    projects.close()


def test_preview_service_reuses_valid_cache_and_rebuilds_corruption(tmp_path: Path) -> None:
    projects = ProjectService(tmp_path)
    project = projects.create("preview-cache")
    root = tmp_path / project.project_dir
    graph = _graph(project.id)
    RenderGraphSnapshotStore(root).set_current(project.id, graph)
    executions = 0

    def execute(
        _: RenderGraphV2,
        output_dir: Path,
        __: PersistentRenderExecutionContext,
    ) -> Path:
        nonlocal executions
        executions += 1
        output_dir.mkdir(parents=True)
        video = output_dir / "preview.mp4"
        video.write_bytes(b"valid-preview")
        return video

    def probe(path: Path) -> MediaProbeResult:
        if path.read_bytes() != b"valid-preview":
            raise RuntimeError("corrupt cache")
        return _valid_probe(path)

    service = AuthoritativePreviewService(
        projects, executor=execute, artifact_probe=probe
    )
    request = AuthoritativePreviewJobRequest(
        graph_id=graph.graph_id,
        graph_hash=graph.graph_hash,
        start_us=1_000_000,
        end_us=2_000_000,
    )
    first = service.submit(project.id, request)
    claimed = projects.jobs.claim_next(JobType.RENDER_PREVIEW)
    assert claimed is not None
    service.handle(claimed)

    reused = service.submit(project.id, request)
    assert reused.id == first.id
    assert executions == 1

    manifest = projects.jobs.get(first.id).result["manifest"]  # type: ignore[index]
    (root / manifest["video_relative_path"]).write_bytes(b"corrupt")
    rebuilt = service.submit(project.id, request)
    assert rebuilt.id != first.id
    claimed = projects.jobs.claim_next(JobType.RENDER_PREVIEW)
    assert claimed is not None
    service.handle(claimed)
    assert executions == 2
    projects.close()
