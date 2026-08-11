from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from workbench.rendering.compiler import RenderGraphCompiler
from workbench.rendering.hashing import sha256_json
from workbench.rendering.legacy_adapter import LegacyAdapterIssue, LegacyProjectAdapter
from workbench.rendering.models import RenderGraphV2, ResolvedAsset, SubtitleRenderPlan
from workbench.timeline.production import ProductionTimeline

from .journal import (
    MigrationJournal,
    MigrationJournalRecord,
    MigrationStage,
)


class ProjectMigrationError(RuntimeError):
    pass


class MigrationAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    relative_path: str
    estimated_bytes: int = Field(ge=0)


class ProjectMigrationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "1.0"
    project_id: UUID
    source_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_hashes: dict[str, str]
    actions: tuple[MigrationAction, ...]
    issues: tuple[LegacyAdapterIssue, ...]
    required_bytes: int = Field(ge=0)
    backup_instructions: str
    rollback_instructions: str
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @property
    def migratable(self) -> bool:
        return not any(issue.severity == "blocking" for issue in self.issues)


class ProjectMigrationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    project_id: UUID
    plan_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    bundle_relative_path: str
    pointer_relative_path: str
    graph_id: UUID
    graph_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    committed: bool


MigrationFaultHook = Callable[[MigrationStage], None]


class ProjectV2Migration:
    def __init__(
        self,
        project_root: Path,
        *,
        fault_hook: MigrationFaultHook | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.fault_hook = fault_hook
        self.adapter = LegacyProjectAdapter(self.project_root)

    def preview(self, payload: Mapping[str, Any]) -> ProjectMigrationPlan:
        view = self.adapter.open(payload)
        graph = _migration_graph(view.timeline, view.assets, view.subtitles)
        documents = {
            "timeline.json": view.timeline.model_dump(mode="json"),
            "subtitles.json": view.subtitles.model_dump(mode="json"),
            "assets.json": [asset.model_dump(mode="json") for asset in view.assets],
            "render-graph.json": graph.model_dump(mode="json"),
            "source-hashes.json": view.source_hashes,
        }
        actions = tuple(
            MigrationAction(
                kind="write_v2_snapshot",
                relative_path=f"07_视频工程/migrations/{{plan_hash}}/{name}",
                estimated_bytes=len(_canonical_json(document).encode("utf-8")),
            )
            for name, document in documents.items()
        )
        base = {
            "schema_version": "1.0",
            "project_id": str(view.project_id),
            "source_manifest_hash": view.manifest_hash,
            "source_hashes": view.source_hashes,
            "issues": [issue.model_dump(mode="json") for issue in view.issues],
            "backup_instructions": "Back up the complete legacy project directory before commit.",
            "rollback_instructions": (
                "Mark v2-migration.json inactive; keep the migration bundle for diagnostics."
            ),
        }
        required_bytes = sum(action.estimated_bytes for action in actions) * 2 + 1_048_576
        plan_hash = sha256_json(
            {
                **base,
                "actions": [action.model_dump(mode="json") for action in actions],
                "required_bytes": required_bytes,
            }
        )
        return ProjectMigrationPlan(
            project_id=view.project_id,
            source_manifest_hash=view.manifest_hash,
            source_hashes=view.source_hashes,
            actions=tuple(
                action.model_copy(
                    update={
                        "relative_path": action.relative_path.replace("{plan_hash}", plan_hash)
                    }
                )
                for action in actions
            ),
            issues=view.issues,
            required_bytes=required_bytes,
            backup_instructions=str(base["backup_instructions"]),
            rollback_instructions=str(base["rollback_instructions"]),
            plan_hash=plan_hash,
        )

    def execute(
        self, plan: ProjectMigrationPlan, payload: Mapping[str, Any]
    ) -> ProjectMigrationResult:
        refreshed = self.preview(payload)
        if refreshed.plan_hash != plan.plan_hash:
            raise ProjectMigrationError("legacy project changed after migration preview")
        if not plan.migratable:
            raise ProjectMigrationError("migration plan has blocking legacy issues")
        free_bytes = shutil.disk_usage(self.project_root).free
        if free_bytes < plan.required_bytes:
            raise ProjectMigrationError("insufficient disk space for migration")
        video_root = self.project_root / "07_视频工程"
        staging = video_root / f".migration-{plan.plan_hash}"
        final = video_root / "migrations" / plan.plan_hash
        pointer = video_root / "v2-migration.json"
        journal = MigrationJournal(
            video_root / "migration-journals" / f"{plan.plan_hash}.json"
        )
        existing = journal.load()
        record = existing or MigrationJournalRecord(
            project_id=plan.project_id,
            plan_hash=plan.plan_hash,
        )
        committed = _active_pointer(pointer, plan.plan_hash)
        if committed:
            graph = RenderGraphV2.model_validate_json(
                (final / "render-graph.json").read_text(encoding="utf-8")
            )
            return _result(self.project_root, plan, final, pointer, graph)
        try:
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True)
            record = journal.checkpoint(record, MigrationStage.PREPARE)
            self._fault(MigrationStage.PREPARE)

            view = self.adapter.open(payload)
            _write_json(staging / "source-hashes.json", view.source_hashes)
            record = journal.checkpoint(record, MigrationStage.SNAPSHOT)
            self._fault(MigrationStage.SNAPSHOT)

            graph = _migration_graph(view.timeline, view.assets, view.subtitles)
            _write_json(staging / "timeline.json", view.timeline.model_dump(mode="json"))
            _write_json(staging / "subtitles.json", view.subtitles.model_dump(mode="json"))
            _write_json(
                staging / "assets.json",
                [asset.model_dump(mode="json") for asset in view.assets],
            )
            _write_json(staging / "render-graph.json", graph.model_dump(mode="json"))
            _write_json(
                staging / "migration-manifest.json",
                {
                    "schema_version": "1.0",
                    "project_id": str(plan.project_id),
                    "plan_hash": plan.plan_hash,
                    "source_manifest_hash": plan.source_manifest_hash,
                    "source_hashes": plan.source_hashes,
                    "graph_id": str(graph.graph_id),
                    "graph_hash": graph.graph_hash,
                },
            )
            record = journal.checkpoint(record, MigrationStage.WRITE)
            self._fault(MigrationStage.WRITE)

            _validate_bundle(staging, plan)
            if self.adapter.open(payload).source_hashes != plan.source_hashes:
                raise ProjectMigrationError("legacy source hashes changed during migration")
            record = journal.checkpoint(record, MigrationStage.VALIDATE)
            self._fault(MigrationStage.VALIDATE)

            final.parent.mkdir(parents=True, exist_ok=True)
            if final.exists():
                _validate_bundle(final, plan)
                shutil.rmtree(staging)
            else:
                staging.replace(final)
            if pointer.exists() and not _pointer_matches_or_inactive(pointer, plan.plan_hash):
                raise ProjectMigrationError("another V2 migration is already active")
            _write_json(
                pointer,
                {
                    "schema_version": "1.0",
                    "active": True,
                    "project_id": str(plan.project_id),
                    "plan_hash": plan.plan_hash,
                    "bundle_relative_path": final.relative_to(self.project_root).as_posix(),
                    "committed_at": datetime.now(UTC).isoformat(),
                },
            )
            journal.checkpoint(record, MigrationStage.COMMIT)
            self._fault(MigrationStage.COMMIT)
            return _result(self.project_root, plan, final, pointer, graph)
        except Exception as error:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            journal.checkpoint(record, MigrationStage.FAILED, error=str(error))
            raise

    def rollback(self, plan_hash: str) -> None:
        pointer = self.project_root / "07_视频工程" / "v2-migration.json"
        if not pointer.is_file():
            raise ProjectMigrationError("no V2 migration pointer exists")
        payload = json.loads(pointer.read_text(encoding="utf-8"))
        if payload.get("plan_hash") != plan_hash:
            raise ProjectMigrationError("migration pointer does not match rollback plan")
        payload.update(
            {
                "active": False,
                "rolled_back_at": datetime.now(UTC).isoformat(),
            }
        )
        _write_json(pointer, payload)
        journal = MigrationJournal(
            self.project_root
            / "07_视频工程"
            / "migration-journals"
            / f"{plan_hash}.json"
        )
        record = journal.load()
        if record is not None:
            journal.checkpoint(record, MigrationStage.ROLLED_BACK)

    def _fault(self, stage: MigrationStage) -> None:
        if self.fault_hook is not None:
            self.fault_hook(stage)


def _migration_graph(
    timeline: ProductionTimeline,
    assets: tuple[ResolvedAsset, ...],
    subtitles: SubtitleRenderPlan,
) -> RenderGraphV2:
    compiler = RenderGraphCompiler()
    graph = compiler.compile(timeline)
    by_ref = {asset.source_ref: asset for asset in assets}
    nodes = [
        node.model_copy(
            update={
                "asset_id": by_ref[node.source_ref].asset_id,
                "asset_revision": by_ref[node.source_ref].revision,
            }
        )
        if node.source_ref in by_ref
        else node
        for node in graph.nodes
    ]
    dependencies = compiler._cache_dependencies(
        nodes, graph.transitions, subtitles, by_ref, timeline
    )
    ranges = compiler._affected_ranges(graph.transitions, subtitles, nodes)
    source_revisions = {
        **graph.source_revisions,
        "legacy_manifest": timeline.input_fingerprint,
        "legacy_adapter": "1.0",
    }
    draft = graph.model_copy(
        update={
            "nodes": nodes,
            "assets": list(assets),
            "subtitles": subtitles,
            "cache_dependencies": list(dependencies),
            "affected_ranges": ranges,
            "source_revisions": source_revisions,
            "graph_hash": "0" * 64,
        }
    )
    payload = draft.model_dump(mode="json", exclude={"graph_hash", "created_at"})
    return draft.model_copy(update={"graph_hash": sha256_json(payload)})


def _validate_bundle(path: Path, plan: ProjectMigrationPlan) -> None:
    manifest = json.loads((path / "migration-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("plan_hash") != plan.plan_hash:
        raise ProjectMigrationError("migration bundle plan hash mismatch")
    ProductionTimeline.model_validate_json((path / "timeline.json").read_text(encoding="utf-8"))
    SubtitleRenderPlan.model_validate_json(
        (path / "subtitles.json").read_text(encoding="utf-8")
    )
    RenderGraphV2.model_validate_json(
        (path / "render-graph.json").read_text(encoding="utf-8")
    )


def _active_pointer(path: Path, plan_hash: str) -> bool:
    if not path.is_file():
        return False
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("active") is True and payload.get("plan_hash") == plan_hash


def _pointer_matches_or_inactive(path: Path, plan_hash: str) -> bool:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("active") is not True or payload.get("plan_hash") == plan_hash


def _result(
    root: Path,
    plan: ProjectMigrationPlan,
    final: Path,
    pointer: Path,
    graph: RenderGraphV2,
) -> ProjectMigrationResult:
    return ProjectMigrationResult(
        project_id=plan.project_id,
        plan_hash=plan.plan_hash,
        bundle_relative_path=final.relative_to(root).as_posix(),
        pointer_relative_path=pointer.relative_to(root).as_posix(),
        graph_id=graph.graph_id,
        graph_hash=graph.graph_hash,
        committed=True,
    )


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
