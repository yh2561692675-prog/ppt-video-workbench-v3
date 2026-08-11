from __future__ import annotations

from pathlib import Path

import pytest
from workbench.desktop.launcher import InstanceState, LauncherMutex, _read_state, _write_state
from workbench.desktop.release_slots import ReleaseSlots


def test_launcher_state_round_trips_atomically(tmp_path: Path) -> None:
    slots = ReleaseSlots(tmp_path / "app")
    state = InstanceState(
        version="1.0.0",
        launcher_pid=1,
        api_pid=2,
        base_url="http://127.0.0.1:8000",
        health_url="http://127.0.0.1:8000/api/health",
    )

    _write_state(slots, state)

    assert _read_state(slots) == state
    assert not (slots.state_root / "instance.partial").exists()


def test_launcher_uses_an_explicit_acceptance_state_root(tmp_path: Path, monkeypatch) -> None:
    isolated = tmp_path / "isolated-state"
    monkeypatch.setenv("WORKBENCH_STATE_ROOT", str(isolated))

    slots = ReleaseSlots(tmp_path / "app")

    assert slots.state_root == isolated.resolve()


def test_launcher_mutex_blocks_concurrent_start_for_same_app_root(tmp_path: Path) -> None:
    with LauncherMutex(tmp_path / "app"), pytest.raises(
        Exception, match="launcher_start_in_progress"
    ), LauncherMutex(tmp_path / "app"):
        pass
