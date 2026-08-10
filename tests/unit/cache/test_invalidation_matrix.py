from __future__ import annotations

from uuid import UUID, uuid4

from workbench.cache.dependency_graph import DependencyGraph, InvalidationEvent
from workbench.domain.models import PageRecord, ProjectManifest


def _project() -> tuple[ProjectManifest, UUID, UUID]:
    project_id = uuid4()
    first = uuid4()
    second = uuid4()
    return (
        ProjectManifest(
            id=project_id,
            name="缓存矩阵",
            project_dir="缓存矩阵_20260804_0000",
            created_at="2026-08-04T00:00:00Z",
            updated_at="2026-08-04T00:00:00Z",
            pages=[
                PageRecord(id=first, order=1, title="第一页"),
                PageRecord(id=second, order=2, title="第二页"),
            ],
        ),
        first,
        second,
    )


def _page(page_id: UUID, node: str) -> str:
    return f"{node}:{page_id}"


def test_six_event_matrix_preserves_unrelated_pages() -> None:
    project, first, second = _project()
    graph = DependencyGraph()
    first_nodes = {
        _page(first, node) for node in ("narration", "audio", "timeline", "subtitle", "segment")
    }
    second_nodes = {
        _page(second, node) for node in ("narration", "audio", "timeline", "subtitle", "segment")
    }
    all_nodes = {"source", "extraction", "match", "final"} | first_nodes | second_nodes

    cases = [
        (
            InvalidationEvent(kind="page_narration_changed", page_id=first),
            first_nodes - {_page(first, "timeline")},
            second_nodes,
        ),
        (
            InvalidationEvent(kind="page_audio_changed", page_id=first),
            {_page(first, node) for node in ("timeline", "subtitle", "segment")},
            second_nodes,
        ),
        (
            InvalidationEvent(kind="content_changed", affected_page_ids=(first,)),
            {
                "extraction",
                "match",
                _page(first, "narration"),
                _page(first, "audio"),
                _page(first, "timeline"),
                _page(first, "subtitle"),
                _page(first, "segment"),
            },
            second_nodes,
        ),
        (
            InvalidationEvent(kind="template_changed"),
            {_page(page_id, "segment") for page_id in (first, second)},
            (first_nodes | second_nodes)
            - {_page(page_id, "segment") for page_id in (first, second)},
        ),
        (
            InvalidationEvent(kind="heygen_voice_changed", affected_page_ids=(first,)),
            {_page(first, node) for node in ("audio", "timeline", "subtitle", "segment")},
            second_nodes,
        ),
        (
            InvalidationEvent(kind="runtime_upgraded", payload={"incompatible_nodes": ["segment"]}),
            {_page(page_id, "segment") for page_id in (first, second)},
            (first_nodes | second_nodes)
            - {_page(page_id, "segment") for page_id in (first, second)},
        ),
    ]

    for event, expected_rebuild, _preserved_page_nodes in cases:
        plan = graph.invalidate(project, event)
        expected_with_final = expected_rebuild | {"final"}
        assert set(plan.rebuild) == expected_with_final
        assert set(plan.preserve) == all_nodes - expected_with_final


def test_invalidation_plan_is_serializable_and_page_change_does_not_touch_other_page() -> None:
    project, first, second = _project()
    plan = DependencyGraph().invalidate(
        project,
        InvalidationEvent(kind="page_narration_changed", page_id=first),
    )

    assert plan.model_dump(mode="json")["reason"]
    assert all(str(second) not in item for item in plan.rebuild)
