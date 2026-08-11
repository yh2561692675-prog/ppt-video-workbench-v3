"""Feature gates for the RenderGraph V2 migration.

The flags are deliberately conservative: V2 is opt-in and the legacy renderer
remains the default until a project explicitly selects a V2 generation.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Literal

RendererGeneration = Literal["v1", "v2"]


def _enabled(name: str, env: Mapping[str, str | None], default: bool = False) -> bool:
    value = env.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _generation(value: str | None) -> RendererGeneration:
    normalized = (value or "v1").strip().lower()
    if normalized not in {"v1", "v2"}:
        raise ValueError("renderer generation must be 'v1' or 'v2'")
    return normalized  # type: ignore[return-value]


@dataclass(frozen=True)
class RenderFeatureFlags:
    """RenderGraph gates resolved from process and project configuration."""

    compile: bool = False
    preview: bool = False
    export: bool = False
    strict_assets: bool = False
    renderer_generation: RendererGeneration = "v1"

    @classmethod
    def from_environment(cls, env: Mapping[str, str | None] | None = None) -> RenderFeatureFlags:
        values = os.environ if env is None else env
        return cls(
            compile=_enabled("WORKBENCH_RENDERGRAPH_V2_COMPILE", values),
            preview=_enabled("WORKBENCH_RENDERGRAPH_V2_PREVIEW", values),
            export=_enabled("WORKBENCH_RENDERGRAPH_V2_EXPORT", values),
            strict_assets=_enabled("WORKBENCH_RENDERGRAPH_V2_STRICT_ASSETS", values),
            renderer_generation=_generation(values.get("WORKBENCH_RENDERER_GENERATION")),
        )

    def for_project(self, renderer_generation: str | None) -> RenderFeatureFlags:
        """Apply a project-level renderer generation without mutating globals."""

        if renderer_generation is None:
            return self
        return replace(self, renderer_generation=_generation(renderer_generation))

    @property
    def v2_enabled(self) -> bool:
        return self.renderer_generation == "v2" and self.compile

    @property
    def v2_exclusive(self) -> bool:
        """A V2 project must fail explicitly instead of silently falling back."""

        return self.renderer_generation == "v2"

    def require_v2(self) -> None:
        if not self.v2_enabled:
            raise RuntimeError("RenderGraph V2 compile flag is disabled")


# Short alias used by callers that prefer the migration-specific name.
RenderGraphFeatureFlags = RenderFeatureFlags
