from __future__ import annotations

import pytest
from peripheral_host.config import HostSettings
from workbench.settings.peripheral import WorkbenchPeripheralSettings


def _clear_peripheral_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "PERIPHERAL_ENABLED",
        "PERIPHERAL_HOST",
        "PERIPHERAL_PORT",
        "PERIPHERAL_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_settings_default_to_disabled_and_localhost(tmp_path, monkeypatch):
    _clear_peripheral_env(monkeypatch)
    monkeypatch.setenv("WORKBENCH_WORKSPACE", str(tmp_path))

    settings = HostSettings.from_env()

    assert settings.enabled is False
    assert settings.host == "127.0.0.1"
    assert settings.port == 8765
    assert settings.workspace_root == tmp_path.resolve()
    assert settings.database_path == tmp_path.resolve() / "workspace-data" / "peripheral.db"
    assert settings.max_workers == 1


def test_settings_reject_non_loopback_host(tmp_path, monkeypatch):
    _clear_peripheral_env(monkeypatch)
    monkeypatch.setenv("WORKBENCH_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("PERIPHERAL_HOST", "0.0.0.0")

    with pytest.raises(ValueError, match="loopback"):
        HostSettings.from_env()


def test_workbench_peripheral_settings_default_to_disabled(monkeypatch):
    _clear_peripheral_env(monkeypatch)

    settings = WorkbenchPeripheralSettings.from_env()

    assert settings.enabled is False
    assert settings.base_url == "http://127.0.0.1:8765"
    assert settings.timeout_seconds == 3.0
