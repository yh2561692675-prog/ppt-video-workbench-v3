"""Built-in scenario registry used by the debug-program CLI."""

from __future__ import annotations

from typing import Any

SCENARIOS: tuple[dict[str, Any], ...] = (
    {
        "schema_version": "1.0",
        "scenario_id": "DBG-core-001",
        "title": "candidate contract and source provenance",
        "matrix": "pr-full",
        "risk": "P1",
        "platform": "all",
        "owner": "A",
        "feature_flags": ["debug_program"],
        "fixture": "tests/fixtures/debug-program/candidate-golden.json",
        "steps": ["load candidate manifest", "validate hashes", "emit verdict"],
        "destructive": False,
        "paid": False,
        "manual": False,
        "resources": ["python"],
        "cleanup": ["workspace", "cache"],
    },
    {
        "schema_version": "1.0",
        "scenario_id": "DBG-recovery-001",
        "title": "interrupted evidence run is resumable",
        "matrix": "local-e2e",
        "risk": "P1",
        "platform": "all",
        "owner": "A",
        "feature_flags": ["debug_program", "recovery"],
        "fixture": "tests/fixtures/debug-program/run-interrupted.json",
        "steps": ["start attempt", "interrupt process", "recover append-only attempt"],
        "destructive": False,
        "paid": False,
        "manual": False,
        "resources": ["python", "sqlite"],
        "cleanup": ["workspace", "cache", "browser-profile", "office-profile"],
    },
    {
        "schema_version": "1.0",
        "scenario_id": "DBG-release-001",
        "title": "installer and rollback acceptance",
        "matrix": "release",
        "risk": "P0",
        "platform": "windows",
        "owner": "B",
        "feature_flags": ["debug_program", "release"],
        "authorization_scope": "windows-release-lab",
        "steps": ["install candidate", "start", "rollback", "uninstall"],
        "destructive": True,
        "paid": False,
        "manual": True,
        "resources": ["installer", "launcher"],
        "cleanup": ["install-directory", "workspace"],
    },
    {
        "schema_version": "1.0",
        "scenario_id": "DBG-provider-001",
        "title": "real provider contract smoke",
        "matrix": "provider",
        "risk": "P2",
        "platform": "all",
        "owner": "C",
        "feature_flags": ["debug_program", "provider"],
        "authorization_scope": "provider-sandbox",
        "steps": ["check authorization", "invoke provider", "record cost"],
        "destructive": False,
        "paid": True,
        "manual": False,
        "resources": ["network", "provider"],
        "cleanup": ["workspace", "cache"],
    },
)


def list_scenarios(
    *,
    matrix: str | None = None,
    risk: str | None = None,
    platform: str | None = None,
    owner: str | None = None,
    include_restricted: bool = False,
) -> list[dict[str, Any]]:
    result = []
    for scenario in SCENARIOS:
        if matrix and scenario["matrix"] != matrix:
            continue
        if risk and scenario["risk"] != risk:
            continue
        if platform and scenario["platform"] not in {platform, "all"}:
            continue
        if owner and scenario["owner"] != owner:
            continue
        if not include_restricted and (
            scenario["destructive"] or scenario["paid"] or scenario["manual"]
        ):
            continue
        result.append(dict(scenario))
    return result
