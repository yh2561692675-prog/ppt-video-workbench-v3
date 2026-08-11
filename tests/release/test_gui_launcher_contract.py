from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_gui_launcher_is_packaged_without_a_console_and_supervises_loopback_api() -> None:
    launcher = (ROOT / "apps/api/src/workbench/desktop/launcher.py").read_text(encoding="utf-8")
    spec = (ROOT / "apps/api/workbench-launcher.spec").read_text(encoding="utf-8")

    assert "127.0.0.1" in launcher
    assert "/api/health" in launcher
    assert "instance.json" in launcher
    assert "workbench.exe" in launcher
    assert "webbrowser.open" in launcher
    assert "CreateMutexW" in launcher
    assert "STARTUP_ATTEMPTS = 2" in launcher
    assert "slots.rollback()" in launcher
    assert "diagnostics" in launcher
    assert "--wait" in launcher
    assert "console=False" in spec
    assert "workbench-launcher" in spec
