"""Verify RC contract fingerprints and migration routing without runtime dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any


class ContractDriftError(ValueError):
    """Raised when a release contract or migration chain has drifted."""


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ContractDriftError(f"json_invalid:{path.as_posix()}") from error


def _resolve_pointer(document: object, pointer: str) -> object:
    current: Any = document
    if pointer == "#":
        return current
    if not pointer.startswith("#/"):
        raise ContractDriftError("json_pointer_invalid")
    for raw in pointer[2:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def verify_contract_catalog(root: Path) -> dict[str, Any]:
    catalog_path = root / "packages" / "contracts" / "v1-contract-catalog.json"
    catalog = _load(catalog_path)
    if not isinstance(catalog, dict) or catalog.get("schema_version") != "1.0":
        raise ContractDriftError("contract_catalog_version_invalid")
    entries = catalog.get("contracts")
    if not isinstance(entries, list) or not entries:
        raise ContractDriftError("contract_catalog_empty")
    fixture_path = root / str(catalog.get("golden_fixture", ""))
    fixtures = _load(fixture_path)
    openapi = _load(root / "packages" / "contracts" / "openapi.json")
    components = openapi.get("components", {}).get("schemas", {}) if isinstance(openapi, dict) else {}
    fingerprint_payload: list[dict[str, Any]] = []
    names: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ContractDriftError("contract_entry_invalid")
        name = entry.get("name")
        if not isinstance(name, str) or name in names:
            raise ContractDriftError(f"contract_name_invalid:{name}")
        names.append(name)
        schema_info = entry.get("json_schema")
        if not isinstance(schema_info, dict):
            raise ContractDriftError(f"schema_reference_missing:{name}")
        schema_path = root / str(schema_info.get("path", ""))
        if not schema_path.is_file() or _sha256(schema_path) != schema_info.get("sha256"):
            raise ContractDriftError(f"schema_hash_mismatch:{name}")
        schema = _load(schema_path)
        try:
            _resolve_pointer(schema, str(schema_info.get("pointer", "#")))
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ContractDriftError(f"schema_pointer_invalid:{name}") from error
        fixture = fixtures.get("contracts", {}).get(name) if isinstance(fixtures, dict) else None
        if fixture is None or _canonical_hash(fixture) != entry.get("fixture_sha256"):
            raise ContractDriftError(f"fixture_hash_mismatch:{name}")
        typescript = entry.get("typescript")
        if not isinstance(typescript, dict):
            raise ContractDriftError(f"typescript_reference_missing:{name}")
        ts_path = root / str(typescript.get("path", ""))
        symbol = typescript.get("symbol")
        if not ts_path.is_file() or not isinstance(symbol, str):
            raise ContractDriftError(f"typescript_reference_invalid:{name}")
        if not re.search(rf"export\s+(?:interface|type)\s+{re.escape(symbol)}\b", ts_path.read_text(encoding="utf-8")):
            raise ContractDriftError(f"typescript_symbol_missing:{name}")
        component = entry.get("openapi_component")
        if not isinstance(component, str) or component not in components:
            raise ContractDriftError(f"openapi_component_missing:{name}")
        fingerprint_payload.append({"name": name, "version": entry.get("version_value"), "schema_sha256": str(schema_info.get("sha256")), "fixture_sha256": str(entry.get("fixture_sha256"))})
    expected_hash = _canonical_hash(fingerprint_payload)
    if catalog.get("contract_set_sha256") != expected_hash:
        raise ContractDriftError("contract_set_fingerprint_mismatch")
    return {"contract_count": len(names), "contract_set_sha256": expected_hash, "contracts": names}


def verify_migration_chain(root: Path) -> dict[str, Any]:
    migrations_path = root / "apps" / "api" / "src" / "workbench" / "storage" / "migrations.py"
    workspace_path = root / "apps" / "api" / "src" / "workbench" / "storage" / "workspace_db.py"
    migrations = migrations_path.read_text(encoding="utf-8")
    workspace = workspace_path.read_text(encoding="utf-8")
    pairs = [(int(source), int(target)) for source, target in re.findall(r"def migrate_v(\d+)_to_v(\d+)\(", migrations)]
    expected = [(1, 2), (2, 3), (3, 4), (4, 5)]
    if pairs != expected:
        raise ContractDriftError(f"migration_functions_drift:{pairs}")
    for source, target in expected:
        if f"UPDATE schema_meta SET version = {target} WHERE version = {source}" not in migrations:
            raise ContractDriftError(f"migration_update_missing:{source}_{target}")
        if f"migrate_v{source}_to_v{target}" not in workspace:
            raise ContractDriftError(f"migration_route_missing:{source}_{target}")
    if "values(version=5)" not in workspace or "version != 5" not in workspace:
        raise ContractDriftError("migration_current_version_drift")
    return {"current_version": 5, "migration_functions": [f"v{a}->v{b}" for a, b in pairs]}


def verify(root: Path) -> dict[str, Any]:
    return {"schema_version": "1.0", "contracts": verify_contract_catalog(root), "migrations": verify_migration_chain(root)}


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.partial")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify RC contract and migration drift.")
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = verify(args.repository_root.resolve())
        if args.output:
            write_report(args.output, report)
    except (ContractDriftError, OSError) as error:
        print(f"RC_CONTRACTS=BLOCK reason={error}")
        return 1
    print(f"RC_CONTRACTS=PASS contracts={report['contracts']['contract_count']} migration_version={report['migrations']['current_version']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
