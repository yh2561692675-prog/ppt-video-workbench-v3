from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import UUID

from .hashing import sha256_json
from .models import RenderGraphV2


class RenderSnapshotError(RuntimeError):
    pass


class RenderGraphSnapshotStore:
    """Filesystem-backed immutable graph snapshots.

    A render job stores the graph hash and snapshot path. The current pointer is
    intentionally only a pointer, so changing the editor cannot mutate a job's
    input.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.root = self.project_root / "07_视频工程" / "render-graphs"

    def save(self, graph: RenderGraphV2) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = graph.model_dump(mode="json", exclude={"graph_hash", "created_at"})
        if sha256_json(payload) != graph.graph_hash:
            raise RenderSnapshotError("render graph content hash does not match")
        target = self.root / str(graph.graph_id) / "graph.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        content = graph.model_dump_json(indent=2) + "\n"
        if target.is_file():
            try:
                existing = RenderGraphV2.model_validate_json(target.read_text(encoding="utf-8"))
            except Exception as error:  # pragma: no cover - corrupted snapshots are rare
                raise RenderSnapshotError(f"render graph snapshot is corrupt: {target}") from error
            # created_at is intentionally excluded from graph_hash, so a
            # deterministic recompile of the same source revision is an
            # idempotent write even if the compile happened later.
            if existing.graph_hash != graph.graph_hash:
                raise RenderSnapshotError("graph hash collision or immutable snapshot mismatch")
            return target
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.write_text(content, encoding="utf-8")
        # Windows rejects fsync on a read-only handle.  Reopen read/write so
        # the durable write barrier is applied before the atomic replace.
        with temporary.open("r+b") as handle:
            os.fsync(handle.fileno())
        temporary.replace(target)
        return target

    def load(self, graph_id_or_hash: str) -> RenderGraphV2:
        target = self.root / graph_id_or_hash / "graph.json"
        if not target.is_file():
            # Compatibility with the pre-Phase-1 filename layout and callers
            # that only persisted a graph hash.
            legacy_target = self.root / f"graph-{graph_id_or_hash}.json"
            if legacy_target.is_file():
                target = legacy_target
            else:
                for candidate in self.root.glob("*/graph.json"):
                    try:
                        if (
                            RenderGraphV2.model_validate_json(
                                candidate.read_text(encoding="utf-8")
                            ).graph_hash
                            == graph_id_or_hash
                        ):
                            target = candidate
                            break
                    except Exception:
                        continue
        if not target.is_file():
            raise RenderSnapshotError(f"render graph snapshot not found: {graph_id_or_hash}")
        try:
            graph = RenderGraphV2.model_validate_json(target.read_text(encoding="utf-8"))
        except Exception as error:
            raise RenderSnapshotError(f"render graph snapshot is corrupt: {target}") from error
        payload = graph.model_dump(mode="json", exclude={"graph_hash", "created_at"})
        if sha256_json(payload) != graph.graph_hash:
            raise RenderSnapshotError("render graph snapshot content hash does not match")
        if graph_id_or_hash != graph.graph_hash and graph_id_or_hash != str(graph.graph_id):
            raise RenderSnapshotError("render graph snapshot identifier does not match")
        return graph

    def set_current(self, project_id: UUID, graph: RenderGraphV2) -> Path:
        target = self.save(graph)
        pointer = self.root / f"current-{project_id}.json"
        temporary = pointer.with_name(f".{pointer.name}.tmp")
        temporary.write_text(
            json.dumps(
                {
                    "project_id": str(project_id),
                    "graph_id": str(graph.graph_id),
                    "graph_hash": graph.graph_hash,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        with temporary.open("r+b") as handle:
            os.fsync(handle.fileno())
        temporary.replace(pointer)
        return target

    def current(self, project_id: UUID) -> RenderGraphV2:
        pointer = self.root / f"current-{project_id}.json"
        if not pointer.is_file():
            raise RenderSnapshotError(f"current render graph not found: {project_id}")
        payload = json.loads(pointer.read_text(encoding="utf-8"))
        graph = self.load(str(payload.get("graph_id") or payload["graph_hash"]))
        if graph.graph_hash != payload["graph_hash"]:
            raise RenderSnapshotError("current pointer hash does not match snapshot")
        return graph
