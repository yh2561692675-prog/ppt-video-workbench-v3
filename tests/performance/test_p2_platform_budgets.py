from __future__ import annotations

import json
import time
import tracemalloc
from pathlib import Path

from workbench.cache.p2_matrix import P2CacheArtifact, P2InvalidationMatrix
from workbench.sync import SyncClient

ROOT = Path(__file__).parents[2]
BUDGETS = json.loads(
    (ROOT / "docs" / "acceptance" / "p2-platform-performance-budget.json").read_text(
        encoding="utf-8"
    )
)["workloads"]


def _measure(operation):
    tracemalloc.start()
    started = time.perf_counter()
    try:
        result = operation()
        elapsed_ms = (time.perf_counter() - started) * 1000
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return result, elapsed_ms, peak_bytes


def test_thousand_operation_outbox_stays_within_local_resource_budget(
    tmp_path: Path,
) -> None:
    budget = BUDGETS["sync_outbox"]
    client = SyncClient(tmp_path / "sync.db", enabled=True)

    def enqueue_all() -> None:
        for index in range(budget["operations"]):
            assert client.enqueue(f"offline-{index:04d}", {"kind": "page.insert", "index": index})

    _, elapsed_ms, peak_bytes = _measure(enqueue_all)
    assert client.state().pending == budget["operations"]
    assert elapsed_ms <= budget["max_elapsed_ms"]
    assert peak_bytes <= budget["max_peak_bytes"]


def test_thousand_remote_operations_pull_in_bounded_pages(tmp_path: Path) -> None:
    budget = BUDGETS["sync_pull"]
    client = SyncClient(tmp_path / "sync.db", enabled=True)

    class Transport:
        offset = 0

        def list_operations(self, cursor: str | None = None) -> dict[str, object]:
            del cursor
            start = self.offset
            self.offset += budget["page_size"]
            return {
                "items": [
                    {"operation_id": f"remote-{index:04d}", "kind": "page.insert"}
                    for index in range(start, min(self.offset, budget["operations"]))
                ]
            }

    transport = Transport()

    def pull_all() -> None:
        for _ in range(budget["operations"] // budget["page_size"]):
            client.pull(transport, limit=budget["page_size"])  # type: ignore[arg-type]

    _, elapsed_ms, peak_bytes = _measure(pull_all)
    assert client.state().remote_operations == budget["operations"]
    assert elapsed_ms <= budget["max_elapsed_ms"]
    assert peak_bytes <= budget["max_peak_bytes"]


def test_invalidation_matrix_decision_overhead_is_bounded() -> None:
    budget = BUDGETS["invalidation_matrix"]
    matrix = P2InvalidationMatrix()
    artifacts = (
        P2CacheArtifact("source", "content"),
        P2CacheArtifact("llm", "provider_result", "llm"),
        P2CacheArtifact("tts", "media", "tts"),
        P2CacheArtifact("render", "renderer", "renderer"),
        P2CacheArtifact("video", "video"),
        P2CacheArtifact("final", "final"),
    )

    def decide_all() -> int:
        rebuilds = 0
        iterations = budget["decisions"] // len(artifacts)
        for _ in range(iterations):
            rebuilds += sum(
                decision.rebuild
                for decision in matrix.plan("platform_capability_changed", artifacts)
            )
        return rebuilds

    rebuilds, elapsed_ms, peak_bytes = _measure(decide_all)
    assert rebuilds == (budget["decisions"] // len(artifacts)) * 4
    assert elapsed_ms <= budget["max_elapsed_ms"]
    assert peak_bytes <= budget["max_peak_bytes"]
