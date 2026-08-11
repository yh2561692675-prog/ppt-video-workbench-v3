from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[3]
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "rendergraph-v2"


def test_rendergraph_baseline_fixtures_are_local_and_complete() -> None:
    manifest = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
    fixtures = manifest["fixtures"]
    assert len(fixtures) >= 4
    assert {item["id"] for item in fixtures} >= {
        "ai-narration",
        "presenter",
        "vertical",
        "overlay-subtitles",
    }
    for item in fixtures:
        assert item["network_required"] is False
        path = FIXTURE_ROOT / item["path"]
        assert path.is_file()
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["fixture_id"] == item["id"]
        assert payload["legacy_output"]["sha256"] is None
