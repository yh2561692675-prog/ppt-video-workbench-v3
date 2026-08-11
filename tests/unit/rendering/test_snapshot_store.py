from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from workbench.rendering.hashing import sha256_json
from workbench.rendering.models import GraphCanvas, RenderGraphV2
from workbench.rendering.snapshot_store import RenderGraphSnapshotStore, RenderSnapshotError


def _graph() -> RenderGraphV2:
    project_id = uuid4()
    graph = RenderGraphV2(
        graph_id=uuid4(),
        project_id=project_id,
        timeline_revision=1,
        timeline_hash="1" * 64,
        compiler_version="test",
        duration_us=1_000_000,
        canvas=GraphCanvas(width=1920, height=1080, fps=30, duration_us=1_000_000),
        nodes=[],
        transitions=[],
        assets=[],
        audio={"clips": [], "ducking": [], "loudness_target_lufs": -16, "true_peak_db": -1},
        subtitles={"render_mode": "none", "cues": [], "default_style": {}, "languages": []},
        source_revisions={},
        affected_ranges=[],
        graph_hash="0" * 64,
    )
    payload = graph.model_dump(mode="json", exclude={"graph_hash", "created_at"})
    return graph.model_copy(update={"graph_hash": sha256_json(payload)})


def test_snapshot_store_uses_graph_id_directory_and_idempotent_save(tmp_path: Path) -> None:
    store = RenderGraphSnapshotStore(tmp_path)
    graph = _graph()
    path = store.save(graph)
    assert path == tmp_path / "07_视频工程" / "render-graphs" / str(graph.graph_id) / "graph.json"
    assert store.save(graph) == path
    assert store.save(graph.model_copy(update={"created_at": datetime.now(UTC)})) == path
    store.set_current(graph.project_id, graph)
    pointer = json.loads(
        (store.root / f"current-{graph.project_id}.json").read_text(encoding="utf-8")
    )
    assert pointer == {
        "graph_hash": graph.graph_hash,
        "graph_id": str(graph.graph_id),
        "project_id": str(graph.project_id),
    }
    assert store.load(str(graph.graph_id)).graph_hash == graph.graph_hash
    assert store.load(graph.graph_hash).graph_id == graph.graph_id


def test_snapshot_store_rejects_corrupt_json_and_hash_mismatch(tmp_path: Path) -> None:
    store = RenderGraphSnapshotStore(tmp_path)
    graph = _graph()
    path = store.save(graph)
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(RenderSnapshotError, match="corrupt"):
        store.load(str(graph.graph_id))

    path.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["timeline_revision"] = 99
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RenderSnapshotError, match="content hash"):
        store.load(str(graph.graph_id))
