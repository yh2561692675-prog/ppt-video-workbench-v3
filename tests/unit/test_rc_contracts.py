from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("verify_rc_contracts", ROOT / "scripts" / "verify_rc_contracts.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_contract_catalog_and_migration_chain_are_current() -> None:
    report = MODULE.verify(ROOT)
    assert report["contracts"]["contract_count"] == 10
    assert report["migrations"]["current_version"] == 5


def test_contract_drift_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "packages" / "contracts").mkdir(parents=True)
    (tmp_path / "packages" / "contracts" / "v1-contract-catalog.json").write_text("{}", encoding="utf-8")
    with pytest.raises(MODULE.ContractDriftError, match="contract_catalog_version_invalid"):
        MODULE.verify_contract_catalog(tmp_path)
