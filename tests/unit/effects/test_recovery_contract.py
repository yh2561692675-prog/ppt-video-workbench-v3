from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from workbench.effects.release_gate import summarize_release  # noqa: E402
from workbench.effects.release_models import ValidationError  # noqa: E402


def test_release_gate_requires_ordered_gates() -> None:
    payload = [{"gate_id": f"G{i}", "passed": True, "reason_codes": []} for i in range(7)]
    assert summarize_release(payload)["passed"] is True


def test_release_gate_rejects_extra_fields() -> None:
    payload = [{"gate_id": "G0", "passed": True, "reason_codes": [], "bypass": True}]
    try:
        summarize_release(payload)
    except ValidationError as exc:
        assert "extra_fields" in str(exc)
    else:
        raise AssertionError("extra fields were accepted")


def test_frozen_assets_are_json() -> None:
    for rel in (
        "fixtures/effects/education-v2/manifest.json",
        "fixtures/effects/education-v2/ground-truth.json",
        "docs/effects/visual-review.json",
        "docs/effects/release-candidate-manifest.json",
    ):
        json.loads((ROOT / rel).read_text(encoding="utf-8"))
