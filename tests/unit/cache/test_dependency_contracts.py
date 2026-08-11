from __future__ import annotations

import json
from pathlib import Path

from workbench.cache.contracts import CacheDependency, CacheDomain, normalize_dependencies


def test_cache_dependency_fixture_round_trips_and_normalizes() -> None:
    fixture = json.loads(
        Path("tests/fixtures/cache-dependency-v1.json").read_text(encoding="utf-8")
    )
    schema = json.loads(
        Path("schemas/cache-dependency-v1.schema.json").read_text(encoding="utf-8")
    )
    dependency = CacheDependency.model_validate(fixture)
    other = dependency.model_copy(
        update={"node_key": "audio:node-2", "domain": CacheDomain.AUDIO}
    )

    normalized = normalize_dependencies([dependency, other])

    assert [item.node_key for item in normalized] == ["audio:node-2", "visual:node-1"]
    assert CacheDependency.model_validate_json(dependency.model_dump_json()) == dependency
    assert len(dependency.dependency_key) == 64
    assert schema["title"] == "CacheDependencyV1"
    assert set(schema["required"]) == set(fixture)
