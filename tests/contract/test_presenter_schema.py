import json
from pathlib import Path
from uuid import uuid4

from workbench.domain.presenter import PresenterTimelineV1

ROOT = Path(__file__).resolve().parents[2]


def test_presenter_timeline_schema_matches_python_contract() -> None:
    committed = json.loads(
        (ROOT / "schemas" / "presenter-timeline.schema.json").read_text(encoding="utf-8")
    )

    assert committed == PresenterTimelineV1.model_json_schema()


def test_presenter_timeline_sample_validates_against_json_schema() -> None:
    schema = PresenterTimelineV1.model_json_schema()
    sample = {
        "schema_version": "1.0",
        "revision": 1,
        "source_id": str(uuid4()),
        "source_version": "a" * 64,
        "duration_ms": 10_000,
        "anchors": [],
        "segments": [],
        "unassigned_ranges": [],
    }

    assert schema["$defs"]
    validated = PresenterTimelineV1.model_validate(sample)
    assert validated.model_dump(mode="json", exclude_none=True) == sample
