from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException

from workbench.api.projects import Envelope, envelope
from workbench.assets.models import AssetRecord
from workbench.continuity.models import ContinuityPlan
from workbench.domain.models import JobRecord
from workbench.rendering.compiler import RenderGraphCompiler
from workbench.rendering.models import AffectedRange, RenderGraphV2
from workbench.rendering.preflight import GraphPreflight, GraphPreflightReport
from workbench.rendering.preview import (
    PreviewRangeError,
    RenderGraphPreviewPlan,
    RenderGraphPreviewRequest,
    build_preview_plan,
)
from workbench.rendering.preview_service import (
    AuthoritativePreviewJobRequest,
    AuthoritativePreviewService,
    PreviewSubmissionBlocked,
)
from workbench.rendering.snapshot_store import RenderGraphSnapshotStore, RenderSnapshotError
from workbench.subtitles.workbench_models import SubtitleWorkbenchDocument
from workbench.timeline.production import (
    ProductionTimeline,
    RenderGraph,
    TimelineCommand,
    TimelineCommandBatch,
    TimelineCompiler,
    TimelineEditor,
    TimelineError,
)


class TimelineWorkspaceService:
    def __init__(
        self,
        root: Path | None = None,
        project_dir_resolver: Callable[[UUID], str] | None = None,
    ) -> None:
        self.root = root.resolve() if root is not None else None
        self.project_dir_resolver = project_dir_resolver
        self._editors: dict[UUID, TimelineEditor] = {}
        self._graphs: dict[UUID, RenderGraph] = {}
        self._graphs_v2: dict[UUID, RenderGraphV2] = {}
        self.compiler = TimelineCompiler()
        self.v2_compiler = RenderGraphCompiler()

    def initialize(self, timeline: ProductionTimeline) -> ProductionTimeline:
        editor = TimelineEditor(timeline)
        self._editors[timeline.project_id] = editor
        self._graphs.pop(timeline.project_id, None)
        self._graphs_v2.pop(timeline.project_id, None)
        self._persist(timeline)
        return editor.timeline

    def get(self, project_id: UUID) -> ProductionTimeline:
        if project_id not in self._editors:
            self._load(project_id)
        try:
            return self._editors[project_id].timeline
        except KeyError as error:
            raise KeyError(project_id) from error

    def apply(self, project_id: UUID, command: TimelineCommand) -> ProductionTimeline:
        timeline = self._editor(project_id).apply(command)
        self._persist(timeline)
        return timeline

    def apply_batch(self, project_id: UUID, batch: TimelineCommandBatch) -> ProductionTimeline:
        timeline = self._editor(project_id).apply_batch(batch)
        self._persist(timeline)
        return timeline

    def compile(self, project_id: UUID) -> RenderGraph:
        graph = self.compiler.compile(self._editor(project_id).timeline)
        self._graphs[project_id] = graph
        return graph

    def compile_v2(
        self,
        project_id: UUID,
        *,
        expected_revision: int | None = None,
        continuity: ContinuityPlan | None = None,
        subtitles: SubtitleWorkbenchDocument | None = None,
        assets: list[AssetRecord] | None = None,
    ) -> RenderGraphV2:
        timeline = self._editor(project_id).timeline
        if expected_revision is not None and timeline.revision != expected_revision:
            raise TimelineError(
                "timeline_revision_conflict",
                f"timeline revision is {timeline.revision}, expected {expected_revision}",
            )
        project_root = self._project_root(project_id) if self.root is not None else None
        graph = self.v2_compiler.compile(
            timeline,
            # A persisted workspace compile resolves every source_ref even
            # when no asset catalog has been attached yet, so missing files
            # become explicit preflight failures instead of silent metadata.
            continuity=continuity,
            subtitles=subtitles,
            assets=assets if assets is not None else ([] if project_root is not None else None),
            project_root=project_root,
            source_revisions={"timeline_revision": str(timeline.revision)},
        )
        self._graphs_v2[project_id] = graph
        if project_root is not None:
            RenderGraphSnapshotStore(project_root).set_current(project_id, graph)
        return graph

    def restore(
        self, project_id: UUID, revision: int, expected_revision: int
    ) -> ProductionTimeline:
        editor = self._editor(project_id)
        revision_path = self._revision_path(project_id, revision)
        if revision not in editor._history and revision_path.is_file():
            editor._history[revision] = ProductionTimeline.model_validate_json(
                revision_path.read_text(encoding="utf-8")
            )
        timeline = editor.restore(revision, expected_revision)
        self._persist(timeline)
        return timeline

    def revisions(self, project_id: UUID) -> list[int]:
        self._load(project_id)
        return sorted(self._editor(project_id)._history)

    def _editor(self, project_id: UUID) -> TimelineEditor:
        if project_id not in self._editors:
            self._load(project_id)
        try:
            return self._editors[project_id]
        except KeyError as error:
            raise KeyError(project_id) from error

    def _project_root(self, project_id: UUID) -> Path:
        if self.root is None:
            raise KeyError(project_id)
        project_dir = (
            self.project_dir_resolver(project_id)
            if self.project_dir_resolver is not None
            else str(project_id)
        )
        base = (self.root / project_dir).resolve()
        base.mkdir(parents=True, exist_ok=True)
        return base

    def _revision_path(self, project_id: UUID, revision: int) -> Path:
        return (
            self._project_root(project_id)
            / "07_瑙嗛宸ョ▼"
            / "timeline-revisions"
            / f"revision-{revision}.json"
        )

    def _persist(self, timeline: ProductionTimeline) -> None:
        if self.root is None:
            return
        target = self._revision_path(timeline.project_id, timeline.revision)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(timeline.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)
        current = target.parent / "current.json"
        current_temporary = current.with_suffix(".tmp")
        current_temporary.write_text(timeline.model_dump_json(indent=2) + "\n", encoding="utf-8")
        current_temporary.replace(current)

    def _load(self, project_id: UUID) -> None:
        if self.root is None:
            raise KeyError(project_id)
        current = (
            self._project_root(project_id) / "07_瑙嗛宸ョ▼" / "timeline-revisions" / "current.json"
        )
        if not current.is_file():
            raise KeyError(project_id)
        timeline = ProductionTimeline.model_validate_json(current.read_text(encoding="utf-8"))
        editor = TimelineEditor(timeline)
        for path in current.parent.glob("revision-*.json"):
            try:
                revision = int(path.stem.removeprefix("revision-"))
                editor._history[revision] = ProductionTimeline.model_validate_json(
                    path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        self._editors[project_id] = editor


def create_timeline_router(
    service: TimelineWorkspaceService,
    preview_jobs: AuthoritativePreviewService | None = None,
    compile_v2_with_context: Callable[[UUID, int | None], RenderGraphV2] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/projects/{project_id}")

    def compile_v2_for_route(
        project_id: UUID, expected_revision: int | None = None
    ) -> RenderGraphV2:
        if compile_v2_with_context is not None:
            return compile_v2_with_context(project_id, expected_revision)
        return service.compile_v2(project_id, expected_revision=expected_revision)

    @router.get("/timeline", response_model=Envelope[ProductionTimeline | None])
    def get_timeline(project_id: UUID) -> Envelope[ProductionTimeline | None]:
        try:
            return envelope(service.get(project_id))
        except KeyError:
            # Reaching the production step precedes the first timeline
            # initialization. This lifecycle state is an empty resource.
            return envelope(None)

    @router.post(
        "/timeline/initialize", response_model=Envelope[ProductionTimeline], status_code=201
    )
    def initialize(project_id: UUID, timeline: ProductionTimeline) -> Envelope[ProductionTimeline]:
        if timeline.project_id != project_id:
            raise HTTPException(status_code=422, detail="project id does not match timeline")
        return envelope(service.initialize(timeline))

    @router.post("/timeline/commands", response_model=Envelope[ProductionTimeline])
    def command(project_id: UUID, request: TimelineCommand) -> Envelope[ProductionTimeline]:
        try:
            return envelope(service.apply(project_id, request))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="timeline not found") from error
        except TimelineError as error:
            raise HTTPException(
                status_code=409, detail={"code": error.code, "message": str(error)}
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_timeline", "message": str(error)},
            ) from error

    @router.post("/timeline/commands:batch", response_model=Envelope[ProductionTimeline])
    def batch_command(
        project_id: UUID, request: TimelineCommandBatch
    ) -> Envelope[ProductionTimeline]:
        try:
            return envelope(service.apply_batch(project_id, request))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="timeline not found") from error
        except TimelineError as error:
            raise HTTPException(
                status_code=409, detail={"code": error.code, "message": str(error)}
            ) from error
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail={"code": "invalid_timeline", "message": str(error)},
            ) from error

    @router.post("/timeline/compile", response_model=Envelope[RenderGraph])
    def compile(project_id: UUID) -> Envelope[RenderGraph]:
        try:
            return envelope(service.compile(project_id))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="timeline not found") from error

    @router.post("/timeline/compile-v2", response_model=Envelope[RenderGraphV2])
    def compile_v2(
        project_id: UUID, expected_revision: int | None = None
    ) -> Envelope[RenderGraphV2]:
        try:
            return envelope(compile_v2_for_route(project_id, expected_revision))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="timeline not found") from error
        except TimelineError as error:
            raise HTTPException(
                status_code=409, detail={"code": error.code, "message": str(error)}
            ) from error

    @router.get("/timeline/revisions", response_model=Envelope[list[int]])
    def revisions(project_id: UUID) -> Envelope[list[int]]:
        try:
            return envelope(service.revisions(project_id))
        except KeyError:
            return envelope([])

    @router.post(
        "/timeline/revisions/{revision}/restore", response_model=Envelope[ProductionTimeline]
    )
    def restore(
        project_id: UUID, revision: int, expected_revision: int
    ) -> Envelope[ProductionTimeline]:
        try:
            return envelope(service.restore(project_id, revision, expected_revision))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="timeline not found") from error
        except TimelineError as error:
            raise HTTPException(
                status_code=409, detail={"code": error.code, "message": str(error)}
            ) from error

    @router.get("/render-graph", response_model=Envelope[RenderGraph])
    def render_graph(project_id: UUID) -> Envelope[RenderGraph]:
        try:
            return envelope(service._graphs[project_id])
        except KeyError as error:
            raise HTTPException(status_code=404, detail="render graph not compiled") from error

    @router.get("/render-graph-v2", response_model=Envelope[RenderGraphV2 | None])
    def render_graph_v2(project_id: UUID) -> Envelope[RenderGraphV2 | None]:
        try:
            graph = service._graphs_v2.get(project_id)
            if graph is None and service.root is not None:
                graph = RenderGraphSnapshotStore(service._project_root(project_id)).current(
                    project_id
                )
            if graph is None:
                return envelope(None)
            return envelope(graph)
        except RenderSnapshotError:
            return envelope(None)

    @router.post("/render-graphs:compile", response_model=Envelope[RenderGraphV2])
    def compile_render_graph(
        project_id: UUID, expected_revision: int | None = None
    ) -> Envelope[RenderGraphV2]:
        try:
            return envelope(compile_v2_for_route(project_id, expected_revision))
        except KeyError as error:
            raise HTTPException(status_code=404, detail="timeline not found") from error
        except TimelineError as error:
            raise HTTPException(
                status_code=409, detail={"code": error.code, "message": str(error)}
            ) from error

    @router.get("/render-graphs/current", response_model=Envelope[RenderGraphV2 | None])
    def current_render_graph(project_id: UUID) -> Envelope[RenderGraphV2 | None]:
        try:
            graph = service._graphs_v2.get(project_id)
            if graph is None and service.root is not None:
                graph = RenderGraphSnapshotStore(service._project_root(project_id)).current(
                    project_id
                )
            if graph is None:
                raise KeyError(project_id)
            return envelope(graph)
        except (KeyError, RenderSnapshotError):
            # A graph is optional until the timeline has been compiled.  Treat
            # that expected lifecycle state as an empty resource rather than a
            # failed browser request (and reserve 404 for unknown concrete IDs).
            return envelope(None)

    @router.get("/render-graphs/{graph_id}", response_model=Envelope[RenderGraphV2])
    def get_render_graph(project_id: UUID, graph_id: UUID) -> Envelope[RenderGraphV2]:
        try:
            graph = service._graphs_v2.get(project_id)
            if graph is not None and graph.graph_id == graph_id:
                return envelope(graph)
            if service.root is None:
                raise KeyError(graph_id)
            graph = RenderGraphSnapshotStore(service._project_root(project_id)).load(str(graph_id))
            if graph.project_id != project_id:
                raise KeyError(graph_id)
            return envelope(graph)
        except (KeyError, RenderSnapshotError) as error:
            raise HTTPException(status_code=404, detail="RenderGraph V2 not found") from error

    @router.get(
        "/render-graphs/{graph_id}/preflight", response_model=Envelope[GraphPreflightReport]
    )
    def preflight_render_graph(project_id: UUID, graph_id: UUID) -> Envelope[GraphPreflightReport]:
        graph = get_render_graph(project_id, graph_id).data
        project_root = service._project_root(project_id) if service.root is not None else Path(".")
        return envelope(GraphPreflight().check(graph, project_root))

    @router.get(
        "/render-graphs/{graph_id}/affected-ranges",
        response_model=Envelope[list[AffectedRange]],
    )
    def affected_ranges(project_id: UUID, graph_id: UUID) -> Envelope[list[AffectedRange]]:
        graph = get_render_graph(project_id, graph_id).data
        return envelope(list(graph.affected_ranges))

    @router.post(
        "/render-graphs/{graph_id}/preview-plan",
        response_model=Envelope[RenderGraphPreviewPlan],
    )
    def preview_plan(
        project_id: UUID, graph_id: UUID, request: RenderGraphPreviewRequest
    ) -> Envelope[RenderGraphPreviewPlan]:
        graph = get_render_graph(project_id, graph_id).data
        try:
            return envelope(build_preview_plan(graph, request))
        except PreviewRangeError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.post(
        "/render-graphs/{graph_id}/preview-jobs",
        response_model=Envelope[JobRecord],
        status_code=202,
    )
    def create_preview_job(
        project_id: UUID,
        graph_id: UUID,
        request: AuthoritativePreviewJobRequest,
    ) -> Envelope[JobRecord]:
        if preview_jobs is None:
            raise HTTPException(status_code=503, detail="preview worker unavailable")
        if request.graph_id != graph_id:
            raise HTTPException(status_code=422, detail="graph id does not match route")
        try:
            return envelope(preview_jobs.submit(project_id, request))
        except PreviewSubmissionBlocked as error:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "preview_preflight_blocked",
                    "message": str(error),
                    "issues": [item.model_dump(mode="json") for item in error.report.issues],
                },
            ) from error
        except (KeyError, RenderSnapshotError) as error:
            raise HTTPException(status_code=404, detail="RenderGraph V2 not found") from error
        except (PreviewRangeError, ValueError) as error:
            raise HTTPException(
                status_code=422,
                detail={"code": "preview_request_invalid", "message": str(error)},
            ) from error

    return router
