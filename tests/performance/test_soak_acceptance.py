from __future__ import annotations

import json

import pytest
from workbench.performance.soak_acceptance import (
    _DEFAULT_PAGE_DURATION_MS,
    _candidate_run_root,
    _cycle_mode,
    _require_windows_path_budget,
    _RotatingLedger,
    _temporary_file_count,
    _validate_options,
)


def test_soak_fixture_page_duration_is_integral_at_the_qualified_24fps_rate() -> None:
    assert _DEFAULT_PAGE_DURATION_MS * 24 % 1_000 == 0


def test_soak_cycle_modes_prioritize_cancel_retry_then_recovery() -> None:
    assert _cycle_mode(1, recovery_every=3, cancellation_every=5) == "normal"
    assert _cycle_mode(3, recovery_every=3, cancellation_every=5) == "recovery"
    assert _cycle_mode(5, recovery_every=3, cancellation_every=5) == "cancel_retry"
    assert _cycle_mode(15, recovery_every=3, cancellation_every=5) == "cancel_retry"


def test_soak_candidate_root_is_short_and_hash_bound(tmp_path) -> None:
    root = _candidate_run_root(tmp_path, "c" * 64, "r-soak-20260813T032054Z-1a16dffb")
    assert root == tmp_path / "c-cccccccccccc" / "r-soak-20260813T032054Z-1a16dffb"
    _require_windows_path_budget(
        _candidate_run_root(tmp_path.drive + "/x", "c" * 64, "r-soak-20260813T032054Z-1a16dffb")
    )


def test_soak_rejects_invalid_run_options() -> None:
    with pytest.raises(ValueError, match="minimum_cycles"):
        _validate_options(
            duration_seconds=0,
            minimum_cycles=0,
            cycle_interval_seconds=0,
            page_count=1,
            recovery_every=0,
            cancellation_every=0,
        )


def test_soak_ledger_rotates_without_overwriting(tmp_path) -> None:
    ledger = _RotatingLedger(tmp_path, max_segment_bytes=100)
    ledger.append({"cycle": 1, "payload": "a" * 80})
    ledger.append({"cycle": 2, "payload": "b" * 80})

    assert len(ledger.paths) == 2
    assert [json.loads(path.read_text(encoding="utf-8")) for path in ledger.paths] == [
        {"cycle": 1, "payload": "a" * 80},
        {"cycle": 2, "payload": "b" * 80},
    ]


def test_soak_temporary_count_detects_atomic_media_publication_names(tmp_path) -> None:
    (tmp_path / ".page-0001.tmp.mp4").write_bytes(b"partial media")
    (tmp_path / ".final.json.tmp").write_text("{}", encoding="utf-8")
    assert _temporary_file_count(tmp_path) == 2
