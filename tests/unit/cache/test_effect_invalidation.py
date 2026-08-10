from __future__ import annotations

from cache.dependency_graph import EffectDependencyGraph


def test_source_change_invalidates_only_dependent_effect_plans() -> None:
    graph = EffectDependencyGraph()
    graph.register("page-1", {"page-model:1", "background:tech_blue"})
    graph.register("page-2", {"page-model:2", "background:tech_blue"})

    assert graph.invalidate("background:tech_blue") == {"page-1", "page-2"}
    assert graph.invalidate("page-model:1") == {"page-1"}
