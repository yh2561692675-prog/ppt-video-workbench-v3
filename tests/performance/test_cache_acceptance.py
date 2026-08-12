from __future__ import annotations

from workbench.performance.cache_acceptance import execute_s8_cache_cycle


def test_s8_cache_cycle_uses_only_one_selective_rerender(tmp_path) -> None:
    result = execute_s8_cache_cycle(tmp_path / "cache-project")

    assert (result.cold.cache_hits, result.cold.cache_misses) == (0, 8)
    assert (result.warm.cache_hits, result.warm.cache_misses) == (8, 0)
    assert (
        result.selective_invalidation.cache_hits,
        result.selective_invalidation.cache_misses,
    ) == (
        7,
        1,
    )
    assert result.cold.page_graph_hash == result.warm.page_graph_hash
    assert result.warm.page_graph_hash != result.selective_invalidation.page_graph_hash
    assert result.source_before_sha256 != result.source_after_sha256

    cold = {item.page_order: item for item in result.cold.artifacts}
    selective = {item.page_order: item for item in result.selective_invalidation.artifacts}
    assert cold[4].artifact_sha256 != selective[4].artifact_sha256
    assert all(
        cold[page].artifact_sha256 == selective[page].artifact_sha256
        for page in range(1, 9)
        if page != 4
    )
