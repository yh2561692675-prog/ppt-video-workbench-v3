"""Pure release-gate aggregation; no database or secret access."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .release_models import ReleaseGate, ValidationError

GATE_IDS = tuple(f"G{i}" for i in range(7))


def evaluate_gate(gate_id: str, passed: bool, *reason_codes: str) -> dict[str, Any]:
    if gate_id not in GATE_IDS:
        raise ValidationError("unknown_gate_id")
    if type(passed) is not bool:
        raise ValidationError("passed_must_be_boolean")
    if not all(isinstance(code, str) and code for code in reason_codes):
        raise ValidationError("invalid_reason_codes")
    return {"gate_id": gate_id, "passed": passed, "reason_codes": list(reason_codes)}


def summarize_release(gates: list[Mapping[str, Any]]) -> dict[str, Any]:
    result = ReleaseGate.from_dict({"gates": list(gates)})
    return {
        "passed": result.passed,
        "gates": [
            {"gate_id": g.gate_id, "passed": g.passed, "reason_codes": list(g.reason_codes)}
            for g in result.gates
        ],
    }
