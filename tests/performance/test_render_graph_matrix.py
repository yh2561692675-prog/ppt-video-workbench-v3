from __future__ import annotations

from workbench.performance.render_graph_matrix import _candidate_run_root, _create_fixture


def test_rich_graph_fixture_covers_every_render_graph_dp44_feature(tmp_path) -> None:
    fixture = _create_fixture(tmp_path)
    graph = fixture.graph
    assert graph.subtitles.render_mode == "both"
    assert {node.kind for node in graph.nodes} == {"image", "overlay"}
    assert len(graph.transitions) == 1
    assert graph.transitions[0].kind == "dissolve"
    assert len(graph.audio.clips) == 2
    assert fixture.baseline_graph.subtitles.render_mode == "none"
    assert not fixture.baseline_graph.transitions
    assert {node.kind for node in fixture.baseline_graph.nodes} == {"image"}


def test_render_graph_runtime_root_uses_a_short_candidate_manifest_prefix(tmp_path) -> None:
    root = _candidate_run_root(tmp_path, "b" * 64, "r-graph-20260813T030946Z-3fe529be")
    assert root == tmp_path / "c-bbbbbbbbbbbb" / "r-graph-20260813T030946Z-3fe529be"
