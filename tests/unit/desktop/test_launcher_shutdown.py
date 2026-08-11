from __future__ import annotations

import json
from pathlib import Path

from workbench.desktop import launcher


def test_shutdown_uses_platform_terminator_and_removes_state(
    tmp_path: Path, monkeypatch
) -> None:
    app_root = tmp_path / "app"
    state_root = tmp_path / "state"
    state_root.mkdir(parents=True)
    state_path = state_root / "instance.json"
    state_path.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "launcher_pid": 123,
                "api_pid": 456,
                "base_url": "http://127.0.0.1:3000",
                "health_url": "http://127.0.0.1:3000/api/health",
            }
        ),
        encoding="utf-8",
    )
    calls: list[tuple[int, bool]] = []
    monkeypatch.setattr(
        launcher,
        "_terminate_process",
        lambda pid, *, wait: calls.append((pid, wait)),
    )

    assert launcher.shutdown(app_root, wait=True) == 0

    assert calls == [(456, True), (123, True)]
    assert not state_path.exists()


def test_terminate_process_routes_windows_to_win32(monkeypatch) -> None:
    calls: list[tuple[int, bool]] = []
    monkeypatch.setattr(launcher.os, "name", "nt")
    monkeypatch.setattr(
        launcher,
        "_terminate_windows_process",
        lambda pid, *, wait: calls.append((pid, wait)),
    )

    launcher._terminate_process(789, wait=True)

    assert calls == [(789, True)]
