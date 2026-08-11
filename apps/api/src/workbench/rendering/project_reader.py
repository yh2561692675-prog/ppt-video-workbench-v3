from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from workbench.rendering.hashing import sha256_json
from workbench.rendering.legacy_adapter import (
    LegacyFallbackForbidden,
    LegacyProjectAdapter,
    LegacyProjectView,
)
from workbench.rendering.models import RenderGraphV2


class ProjectRenderSourceError(RuntimeError):
    pass


class CompatibilityAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    action: str
    reason: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProjectRenderSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["v2", "legacy"]
    graph: RenderGraphV2 | None = None
    legacy: LegacyProjectView | None = None
    audit: CompatibilityAudit


class ProjectRenderSourceReader:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()

    def open(
        self,
        legacy_payload: dict[str, Any],
        *,
        renderer_generation: Literal["v1", "v2"] = "v1",
        migration_enabled: bool = True,
    ) -> ProjectRenderSource:
        pointer = self.project_root / "07_视频工程" / "v2-migration.json"
        invalid_reason: str | None = None
        if migration_enabled and pointer.is_file():
            try:
                pointer_payload = json.loads(pointer.read_text(encoding="utf-8"))
                if pointer_payload.get("active") is True:
                    graph = self._load_v2(pointer_payload, legacy_payload)
                    return ProjectRenderSource(
                        mode="v2",
                        graph=graph,
                        audit=CompatibilityAudit(
                            action="project_v2_opened",
                            reason=f"active migration {pointer_payload.get('plan_hash')}",
                        ),
                    )
                invalid_reason = "migration pointer is inactive"
            except (
                OSError,
                ValueError,
                KeyError,
                json.JSONDecodeError,
                ProjectRenderSourceError,
            ) as error:
                invalid_reason = f"invalid V2 migration: {error}"
        elif not migration_enabled:
            invalid_reason = "migration feature flag disabled"
        else:
            invalid_reason = "no active V2 migration"
        if renderer_generation == "v2":
            raise LegacyFallbackForbidden(
                f"V2-exclusive project cannot use legacy fallback: {invalid_reason}"
            )
        legacy = LegacyProjectAdapter(self.project_root).open(legacy_payload)
        return ProjectRenderSource(
            mode="legacy",
            legacy=legacy,
            audit=CompatibilityAudit(
                action="legacy_project_fallback",
                reason=invalid_reason or "legacy project",
            ),
        )

    def _load_v2(
        self, pointer: dict[str, Any], legacy_payload: dict[str, Any]
    ) -> RenderGraphV2:
        relative = str(pointer["bundle_relative_path"])
        bundle = _contained(self.project_root, relative)
        manifest = json.loads(
            (bundle / "migration-manifest.json").read_text(encoding="utf-8")
        )
        if manifest.get("plan_hash") != pointer.get("plan_hash"):
            raise ProjectRenderSourceError("migration plan hash mismatch")
        if manifest.get("source_manifest_hash") != sha256_json(legacy_payload):
            raise ProjectRenderSourceError("legacy manifest changed after V2 migration")
        graph = RenderGraphV2.model_validate_json(
            (bundle / "render-graph.json").read_text(encoding="utf-8")
        )
        expected = sha256_json(
            graph.model_dump(mode="json", exclude={"graph_hash", "created_at"})
        )
        if graph.graph_hash != expected or manifest.get("graph_hash") != graph.graph_hash:
            raise ProjectRenderSourceError("V2 graph hash validation failed")
        return graph


def _contained(root: Path, relative_path: str) -> Path:
    candidate = (root / relative_path).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ProjectRenderSourceError("migration bundle escapes project root") from error
    return candidate
