from __future__ import annotations

import hashlib
import importlib
import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).parents[2]
CATALOG_PATH = ROOT / "packages" / "contracts" / "v1-contract-catalog.json"
EXPECTED_CONTRACTS = {
    "project",
    "asset",
    "material",
    "timeline",
    "subtitle",
    "continuity",
    "render_graph",
    "job",
    "export",
    "quality",
}


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _load_catalog() -> dict[str, Any]:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def _model(entry: dict[str, Any]) -> type[BaseModel]:
    module = importlib.import_module(entry["python"]["module"])
    model = getattr(module, entry["python"]["symbol"])
    assert isinstance(model, type) and issubclass(model, BaseModel)
    return model


def _set_path(payload: dict[str, Any], path: str, value: object) -> None:
    parts = path.split(".")
    current: Any = payload
    for part in parts[:-1]:
        current = current[int(part)] if isinstance(current, list) else current[part]
    if isinstance(current, list):
        current[int(parts[-1])] = value
    else:
        current[parts[-1]] = value


def _resolve_pointer(document: object, pointer: str) -> object:
    current: Any = document
    for raw_part in pointer.removeprefix("#/").split("/") if pointer != "#" else []:
        part = raw_part.replace("~1", "/").replace("~0", "~")
        current = current[int(part)] if isinstance(current, list) else current[part]
    return current


def test_v1_catalog_binds_all_authoritative_contract_surfaces() -> None:
    catalog = _load_catalog()
    entries = catalog["contracts"]
    fixtures = json.loads((ROOT / catalog["golden_fixture"]).read_text(encoding="utf-8"))
    openapi = json.loads((ROOT / "packages/contracts/openapi.json").read_text("utf-8"))

    assert catalog["schema_version"] == "1.0"
    assert {entry["name"] for entry in entries} == EXPECTED_CONTRACTS
    assert set(fixtures["contracts"]) == EXPECTED_CONTRACTS

    for entry in entries:
        name = entry["name"]
        fixture = fixtures["contracts"][name]
        schema_path = ROOT / entry["json_schema"]["path"]
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert hashlib.sha256(schema_path.read_bytes()).hexdigest() == entry["json_schema"][
            "sha256"
        ]
        assert isinstance(_resolve_pointer(schema, entry["json_schema"]["pointer"]), dict)
        assert _canonical_hash(fixture) == entry["fixture_sha256"]
        _model(entry).model_validate(fixture)
        assert fixture[entry["version_field"]] == entry["version_value"]

        type_source = (ROOT / entry["typescript"]["path"]).read_text(encoding="utf-8")
        symbol = re.escape(entry["typescript"]["symbol"])
        assert re.search(rf"export\s+(?:interface|type)\s+{symbol}\b", type_source)
        assert entry["openapi_component"] in openapi["components"]["schemas"]


def test_v1_catalog_compatibility_policy_is_enforced_by_python_models() -> None:
    catalog = _load_catalog()
    fixtures = json.loads((ROOT / catalog["golden_fixture"]).read_text(encoding="utf-8"))[
        "contracts"
    ]

    for entry in catalog["contracts"]:
        assert entry["compatibility"] == {
            "unknown_fields": "reject",
            "older_versions": "explicit_migration",
            "invalid_enum": "reject",
        }
        model = _model(entry)
        fixture = fixtures[entry["name"]]

        with pytest.raises(ValidationError):
            model.model_validate({**fixture, "__unknown_contract_field__": True})

        old_version = deepcopy(fixture)
        _set_path(old_version, entry["version_field"], entry["invalid_version"])
        with pytest.raises(ValidationError):
            model.model_validate(old_version)

        invalid_enum = deepcopy(fixture)
        _set_path(invalid_enum, entry["enum_path"], "__invalid_enum__")
        with pytest.raises(ValidationError):
            model.model_validate(invalid_enum)


def test_v1_contract_set_fingerprint_is_deterministic() -> None:
    catalog = _load_catalog()
    fingerprint_payload = [
        {
            "name": entry["name"],
            "version": entry["version_value"],
            "schema_sha256": entry["json_schema"]["sha256"],
            "fixture_sha256": entry["fixture_sha256"],
        }
        for entry in catalog["contracts"]
    ]

    assert _canonical_hash(fingerprint_payload) == catalog["contract_set_sha256"]
