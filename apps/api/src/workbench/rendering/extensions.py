from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .hashing import sha256_json
from .models import RenderGraphV2, RenderNodeV2


class ExtensionKind(StrEnum):
    EFFECTS = "effects"
    PRESENTER = "presenter"
    PERIPHERAL_P03_P12 = "peripheral_p03_p12"


def _enabled(name: str, env: Mapping[str, str | None]) -> bool:
    value = env.get(name)
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ExtensionFeatureFlags:
    """Opt-in gates for extensions that are not part of the V1 graph baseline."""

    effects: bool = False
    presenter: bool = False
    peripheral_p03_p12: bool = False

    @classmethod
    def from_environment(cls, env: Mapping[str, str | None] | None = None) -> ExtensionFeatureFlags:
        values = os.environ if env is None else env
        return cls(
            effects=_enabled("WORKBENCH_RENDERGRAPH_V2_EFFECTS", values),
            presenter=_enabled("WORKBENCH_RENDERGRAPH_V2_PRESENTER", values),
            peripheral_p03_p12=_enabled("WORKBENCH_RENDERGRAPH_V2_PERIPHERAL", values),
        )

    def enabled(self, kind: ExtensionKind) -> bool:
        return {
            ExtensionKind.EFFECTS: self.effects,
            ExtensionKind.PRESENTER: self.presenter,
            ExtensionKind.PERIPHERAL_P03_P12: self.peripheral_p03_p12,
        }[kind]


class ExtensionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RenderExtensionPatch(ExtensionModel):
    """Declarative changes returned by an isolated extension adapter."""

    source_revision: str = Field(min_length=1, max_length=160)
    node_payload_overrides: dict[UUID, dict[str, Any]] = Field(default_factory=dict)
    appended_nodes: list[RenderNodeV2] = Field(default_factory=list)


PatchBuilder = Callable[[RenderGraphV2], RenderExtensionPatch]


@dataclass(frozen=True)
class GraphExtensionAdapter:
    """Source-bound adapter for Effects, Presenter or the P03-P12 perimeter."""

    kind: ExtensionKind
    source_classification: Literal["verified", "reconstructed"]
    source_commit: str
    source_tasks: tuple[str, ...]
    build_patch: PatchBuilder


class AppliedExtensionProvenance(ExtensionModel):
    kind: ExtensionKind
    source_classification: Literal["verified", "reconstructed"]
    source_commit: str = Field(pattern=r"^[0-9a-f]{7,40}$")
    source_tasks: list[str] = Field(default_factory=list)
    source_revision: str
    patch_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RenderExtensionProvenance(ExtensionModel):
    schema_version: Literal["1.0"] = "1.0"
    base_graph_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    effective_graph_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    extensions: list[AppliedExtensionProvenance] = Field(default_factory=list)


@dataclass(frozen=True)
class RenderExtensionResult:
    graph: RenderGraphV2
    provenance: RenderExtensionProvenance


class RenderExtensionError(RuntimeError):
    pass


class RenderExtensionBoundary:
    """Apply extension patches atomically without exposing the base graph to mutation."""

    def __init__(self, flags: ExtensionFeatureFlags | None = None) -> None:
        self.flags = flags or ExtensionFeatureFlags.from_environment()

    def apply(
        self,
        base_graph: RenderGraphV2,
        adapters: list[GraphExtensionAdapter],
    ) -> RenderExtensionResult:
        enabled_adapters = [adapter for adapter in adapters if self.flags.enabled(adapter.kind)]
        if not enabled_adapters:
            return RenderExtensionResult(
                graph=base_graph,
                provenance=RenderExtensionProvenance(
                    base_graph_hash=base_graph.graph_hash,
                    effective_graph_hash=base_graph.graph_hash,
                ),
            )

        working = base_graph.model_copy(deep=True)
        applied: list[AppliedExtensionProvenance] = []
        try:
            for adapter in enabled_adapters:
                # The adapter receives a private copy. Even a badly behaved adapter
                # cannot mutate the authoritative base graph held by the caller.
                patch = adapter.build_patch(working.model_copy(deep=True))
                if not isinstance(patch, RenderExtensionPatch):
                    patch = RenderExtensionPatch.model_validate(patch)
                working = self._apply_patch(working, adapter.kind, patch)
                applied.append(
                    AppliedExtensionProvenance(
                        kind=adapter.kind,
                        source_classification=adapter.source_classification,
                        source_commit=adapter.source_commit,
                        source_tasks=list(adapter.source_tasks),
                        source_revision=patch.source_revision,
                        patch_sha256=sha256_json(patch.model_dump(mode="json")),
                    )
                )
        except Exception as error:
            kind = adapter.kind.value if "adapter" in locals() else "unknown"
            raise RenderExtensionError(
                f"{kind} extension failed; the base RenderGraph was not changed"
            ) from error

        return RenderExtensionResult(
            graph=working,
            provenance=RenderExtensionProvenance(
                base_graph_hash=base_graph.graph_hash,
                effective_graph_hash=working.graph_hash,
                extensions=applied,
            ),
        )

    @staticmethod
    def _apply_patch(
        graph: RenderGraphV2,
        kind: ExtensionKind,
        patch: RenderExtensionPatch,
    ) -> RenderGraphV2:
        by_id = {node.id: node for node in graph.nodes}
        unknown = set(patch.node_payload_overrides) - set(by_id)
        if unknown:
            raise ValueError(
                f"extension patch references unknown nodes: {sorted(map(str, unknown))}"
            )
        nodes: list[RenderNodeV2] = []
        for node in graph.nodes:
            override = patch.node_payload_overrides.get(node.id)
            nodes.append(
                node
                if override is None
                else node.model_copy(update={"payload": {**node.payload, **override}})
            )
        existing_ids = {node.id for node in nodes}
        if any(node.id in existing_ids for node in patch.appended_nodes):
            raise ValueError("extension patch contains a duplicate node id")
        nodes.extend(patch.appended_nodes)
        revisions = {
            **graph.source_revisions,
            f"extension:{kind.value}": patch.source_revision,
        }
        draft = graph.model_copy(
            update={"nodes": nodes, "source_revisions": revisions, "graph_hash": "0" * 64}
        )
        validated = RenderGraphV2.model_validate(draft.model_dump(mode="python"))
        payload = validated.model_dump(mode="json", exclude={"graph_hash", "created_at"})
        return validated.model_copy(update={"graph_hash": sha256_json(payload)})


__all__ = [
    "AppliedExtensionProvenance",
    "ExtensionFeatureFlags",
    "ExtensionKind",
    "GraphExtensionAdapter",
    "RenderExtensionBoundary",
    "RenderExtensionError",
    "RenderExtensionPatch",
    "RenderExtensionProvenance",
    "RenderExtensionResult",
]
