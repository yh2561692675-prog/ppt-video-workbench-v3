from __future__ import annotations

import pytest
from workbench.rendering.feature_flags import RenderFeatureFlags


def test_render_graph_flags_default_to_legacy() -> None:
    flags = RenderFeatureFlags.from_environment({})
    assert flags == RenderFeatureFlags()
    assert not flags.v2_enabled
    assert not flags.v2_exclusive


def test_render_graph_flags_parse_environment_and_project_override() -> None:
    flags = RenderFeatureFlags.from_environment(
        {
            "WORKBENCH_RENDERGRAPH_V2_COMPILE": "true",
            "WORKBENCH_RENDERGRAPH_V2_PREVIEW": "1",
            "WORKBENCH_RENDERGRAPH_V2_EXPORT": "yes",
            "WORKBENCH_RENDERGRAPH_V2_STRICT_ASSETS": "on",
            "WORKBENCH_RENDERER_GENERATION": "v1",
        }
    )
    assert flags.compile and flags.preview and flags.export and flags.strict_assets
    assert flags.for_project("v2").v2_enabled
    assert flags.for_project(None) == flags


def test_v2_requires_explicit_compile_and_never_falls_back() -> None:
    flags = RenderFeatureFlags(renderer_generation="v2")
    assert flags.v2_exclusive
    with pytest.raises(RuntimeError, match="compile flag"):
        flags.require_v2()


@pytest.mark.parametrize("value", ["v3", "legacy"])
def test_unknown_generation_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="renderer generation"):
        RenderFeatureFlags.from_environment({"WORKBENCH_RENDERER_GENERATION": value})
