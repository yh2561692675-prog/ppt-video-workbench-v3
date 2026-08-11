from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from workbench.rendering.models import GraphCanvas, RenderGraphV2

ROOT = Path(__file__).parents[2]


def _graph_payload() -> dict[str, object]:
    project_id = uuid4()
    return {
        "schema_version": "2.0",
        "graph_id": str(uuid4()),
        "project_id": str(project_id),
        "timeline_revision": 1,
        "timeline_hash": "1" * 64,
        "compiler_version": "rendergraph-v2-test",
        "duration_us": 1_000_000,
        "canvas": {
            "width": 1920,
            "height": 1080,
            "fps": 30,
            "fps_num": 30,
            "fps_den": 1,
            "duration_us": 1_000_000,
            "background": "#000000",
            "pixel_format": "yuv420p",
            "aspect_ratio": "16:9",
        },
        "nodes": [],
        "transitions": [],
        "assets": [],
        "audio_mix": {"clips": [], "ducking": [], "loudness_target_lufs": -16, "true_peak_db": -1},
        "subtitle_plan": {
            "render_mode": "none",
            "cues": [],
            "default_style": {},
            "languages": [],
            "document_revision": 1,
            "document_hash": "2" * 64,
            "tracks": [],
        },
        "source_revisions": {"continuity_revision": "1"},
        "affected_ranges": [],
        "content_hash": "3" * 64,
    }


def test_v2_contract_aliases_validate_and_schema_mirrors() -> None:
    payload = _graph_payload()
    graph = RenderGraphV2.model_validate(payload)
    assert graph.schema_version == "2.0"
    assert graph.content_hash == "3" * 64
    assert graph.audio_mix.clips == []
    schema = json.loads(
        (ROOT / "schemas" / "render-graph-v2.schema.json").read_text(encoding="utf-8")
    )
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) >= {"graph_id", "timeline_hash", "compiler_version"}
    contract = json.loads(
        (ROOT / "packages" / "contracts" / "render-graph-v2.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert contract["$ref"] == "../../schemas/render-graph-v2.schema.json"


def test_v2_contract_rejects_unknown_fields_and_invalid_hashes() -> None:
    with pytest.raises(ValidationError):
        RenderGraphV2.model_validate({**_graph_payload(), "unknown": True})
    with pytest.raises(ValidationError):
        RenderGraphV2.model_validate({**_graph_payload(), "content_hash": "bad"})


def test_canvas_accepts_fps_num_without_legacy_fps() -> None:
    canvas = GraphCanvas(width=1920, height=1080, fps_num=30000, fps_den=1001)
    assert canvas.fps == 30000
