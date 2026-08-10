from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_every_acceptance_id_is_in_the_plan_and_evidence_paths_exist() -> None:
    manifest = json.loads(
        (ROOT / "tests" / "acceptance" / "fixtures-manifest.json").read_text(encoding="utf-8")
    )
    plan = (ROOT / "tests" / "acceptance" / "acceptance-plan.md").read_text(encoding="utf-8")
    all_ids = {test_id for item in manifest["requirements"] for test_id in item["test_ids"]}

    assert all(test_id in plan for test_id in all_ids)
    evidence = {path for item in manifest["requirements"] for path in item["evidence"]}
    assert all((ROOT / path).exists() for path in evidence)
