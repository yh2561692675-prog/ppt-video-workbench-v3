from __future__ import annotations

from uuid import uuid4

import pytest
from workbench.domain.enums import JobType
from workbench.jobs.registry import JobExecutorRegistry
from workbench.rendering.extensions import (
    ExtensionFeatureFlags,
    ExtensionKind,
    GraphExtensionAdapter,
    RenderExtensionBoundary,
    RenderExtensionError,
    RenderExtensionPatch,
)
from workbench.rendering.hashing import sha256_json
from workbench.rendering.models import GraphCanvas, RenderGraphV2
from workbench.rendering.runtime_adapter import register_render_release_executor


def _graph() -> RenderGraphV2:
    graph = RenderGraphV2(
        project_id=uuid4(),
        timeline_revision=1,
        duration_us=1_000_000,
        canvas=GraphCanvas(width=1920, height=1080, fps=30),
        graph_hash="0" * 64,
    )
    return graph.model_copy(
        update={
            "graph_hash": sha256_json(
                graph.model_dump(mode="json", exclude={"graph_hash", "created_at"})
            )
        }
    )


def test_extension_flags_default_off_and_preserve_v1_fallback() -> None:
    graph = _graph()
    boundary = RenderExtensionBoundary(ExtensionFeatureFlags.from_environment({}))
    result = boundary.apply(graph, [])
    assert result.graph is graph
    assert result.provenance.base_graph_hash == graph.graph_hash
    assert result.provenance.effective_graph_hash == graph.graph_hash
    assert result.provenance.extensions == []


def test_enabled_extension_is_applied_as_an_atomic_patch() -> None:
    graph = _graph()
    adapter = GraphExtensionAdapter(
        kind=ExtensionKind.EFFECTS,
        source_classification="reconstructed",
        source_commit="3e5f310aee7157486944cc055a0f2d62a9418582",
        source_tasks=("18", "19", "20", "21", "22", "23", "24", "25"),
        build_patch=lambda _: RenderExtensionPatch(source_revision="effects-v2-fixture"),
    )
    result = RenderExtensionBoundary(ExtensionFeatureFlags(effects=True)).apply(graph, [adapter])
    assert result.graph is not graph
    assert result.graph.graph_hash != graph.graph_hash
    assert graph.source_revisions == {}
    assert result.graph.source_revisions["extension:effects"] == "effects-v2-fixture"
    assert result.provenance.extensions[0].source_classification == "reconstructed"


def test_extension_failure_never_mutates_or_silently_degrades_base_graph() -> None:
    graph = _graph()

    def fail(_: RenderGraphV2) -> RenderExtensionPatch:
        raise RuntimeError("renderer rejected presenter media")

    adapter = GraphExtensionAdapter(
        kind=ExtensionKind.PRESENTER,
        source_classification="verified",
        source_commit="e81b455c4903889ac25697a4a030e523adb7650f",
        source_tasks=("presenter",),
        build_patch=fail,
    )
    before = graph.model_dump(mode="json")
    with pytest.raises(RenderExtensionError, match="presenter"):
        RenderExtensionBoundary(ExtensionFeatureFlags(presenter=True)).apply(graph, [adapter])
    assert graph.model_dump(mode="json") == before


def test_b_executor_registration_consumes_frozen_registry_without_replacement() -> None:
    registry = JobExecutorRegistry()
    calls: list[object] = []

    def handler(record: object) -> None:
        calls.append(record)

    register_render_release_executor(registry, handler)
    assert registry.supported() == (JobType.EXPORT_PACKAGE,)
    assert registry.get(JobType.EXPORT_PACKAGE) is handler
    with pytest.raises(ValueError, match="already registered"):
        register_render_release_executor(registry, handler)
