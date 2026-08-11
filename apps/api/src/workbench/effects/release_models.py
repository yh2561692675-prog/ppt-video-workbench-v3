"""Strict release-gate models recovered for the education-v2 effects baseline."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


class ValidationError(ValueError):
    pass


def _keys(data: Mapping[str, Any], allowed: set[str]) -> None:
    extra = set(data) - allowed
    if extra:
        raise ValidationError(f"extra_fields:{','.join(sorted(extra))}")


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    passed: bool
    reason_codes: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GateResult:
        _keys(data, {"gate_id", "passed", "reason_codes"})
        gate_id = data.get("gate_id")
        passed = data.get("passed")
        reasons = data.get("reason_codes", ())
        if not isinstance(gate_id, str) or not gate_id:
            raise ValidationError("invalid_gate_id")
        if type(passed) is not bool:
            raise ValidationError("passed_must_be_boolean")
        if not isinstance(reasons, (list, tuple)) or not all(isinstance(x, str) for x in reasons):
            raise ValidationError("invalid_reason_codes")
        return cls(gate_id, passed, tuple(reasons))


@dataclass(frozen=True)
class ReleaseCandidate:
    rc_id: str
    installer_sha256: str
    installer_relative_path: str
    assets: Mapping[str, str]
    v2_enabled: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReleaseCandidate:
        _keys(
            data,
            {"rc_id", "installer_sha256", "installer_relative_path", "assets", "v2_enabled"},
        )
        rc_id = data.get("rc_id")
        digest = data.get("installer_sha256")
        installer_relative_path = data.get("installer_relative_path")
        assets = data.get("assets")
        enabled = data.get("v2_enabled", False)
        if not isinstance(rc_id, str) or not rc_id:
            raise ValidationError("invalid_rc_id")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValidationError("invalid_installer_sha256")
        if (
            not isinstance(installer_relative_path, str)
            or not installer_relative_path
            or installer_relative_path.startswith("/")
            or ".." in installer_relative_path.replace("\\", "/").split("/")
        ):
            raise ValidationError("invalid_installer_relative_path")
        if not isinstance(assets, dict) or not all(
            isinstance(k, str) and isinstance(v, str) and len(v) == 64 for k, v in assets.items()
        ):
            raise ValidationError("invalid_asset_hashes")
        if type(enabled) is not bool:
            raise ValidationError("v2_enabled_must_be_boolean")
        return cls(rc_id, digest, installer_relative_path, dict(assets), enabled)


@dataclass(frozen=True)
class ReleaseGate:
    gates: tuple[GateResult, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReleaseGate:
        _keys(data, {"gates"})
        raw = data.get("gates")
        if not isinstance(raw, list):
            raise ValidationError("gates_must_be_list")
        gates = tuple(GateResult.from_dict(x) for x in raw)
        ids = [x.gate_id for x in gates]
        if ids != [f"G{i}" for i in range(len(ids))]:
            raise ValidationError("gate_order_invalid")
        return cls(gates)

    @property
    def passed(self) -> bool:
        return bool(self.gates) and all(g.passed for g in self.gates)
