from __future__ import annotations

import json
from pathlib import Path

import pytest
from workbench.e2e.synthetic import SyntheticVideoRenderer

from scripts.dg2_e2e_fixture import (
    CONTRACT_PATH,
    FIXTURE_VERSION,
    FixtureValidationError,
    generate_fixtures,
    validate_fixtures,
)


def test_dg2_s1_and_s8_fixtures_are_synthetic_and_contract_valid(tmp_path: Path) -> None:
    observed = generate_fixtures(tmp_path)
    validated = validate_fixtures(tmp_path)

    assert set(validated) == {"S1", "S8"}
    assert validated == observed
    assert validated["S1"]["page_count"] == 2
    assert validated["S8"]["page_count"] == 8
    assert validated["S8"]["audio"] == {
        "sample_rate": 16_000,
        "channels": 1,
        "duration_ms": 6_000,
    }
    assert all(item["content_policy"] == "synthetic-only" for item in validated.values())


def test_dg2_fixture_validator_fails_closed_on_source_drift(tmp_path: Path) -> None:
    generate_fixtures(tmp_path)
    audio = tmp_path / "s8" / "local-narration.wav"
    audio.write_bytes(audio.read_bytes() + b"unexpected")

    with pytest.raises(FixtureValidationError, match="source hashes"):
        validate_fixtures(tmp_path)


def test_dg2_fixture_contract_is_reviewable_and_versioned() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert contract["fixture_version"] == FIXTURE_VERSION
    assert set(contract["profiles"]) == {"S1", "S8"}
    assert all(
        len(file["sha256"]) == 64
        for profile in contract["profiles"].values()
        for file in profile["files"].values()
    )


def test_synthetic_render_delay_is_explicitly_scoped_and_validated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WORKBENCH_E2E_SYNTHETIC_MODE", raising=False)
    monkeypatch.setenv("WORKBENCH_DG2_RENDER_DELAY_SECONDS", "2")
    assert SyntheticVideoRenderer().delay_seconds == 0

    monkeypatch.setenv("WORKBENCH_E2E_SYNTHETIC_MODE", "true")
    assert SyntheticVideoRenderer().delay_seconds == 2
    monkeypatch.setenv("WORKBENCH_DG2_RENDER_DELAY_SECONDS", "invalid")
    with pytest.raises(ValueError, match="must be numeric"):
        SyntheticVideoRenderer()
