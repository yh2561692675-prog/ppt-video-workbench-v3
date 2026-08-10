from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})


def _read_bool(name: str, *, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError(f"{name} must be 'true' or 'false'")


def _read_port(name: str, *, default: int) -> int:
    raw_value = os.environ.get(name)
    value = default if raw_value is None else int(raw_value)
    if not 1 <= value <= 65535:
        raise ValueError(f"{name} must be between 1 and 65535")
    return value


@dataclass(frozen=True, slots=True)
class HostSettings:
    enabled: bool
    host: str
    port: int
    workspace_root: Path
    database_path: Path
    modules_root: Path
    max_workers: int
    poll_interval_seconds: float
    shutdown_grace_seconds: float

    @classmethod
    def from_env(cls) -> HostSettings:
        workspace_root = Path(os.environ.get("WORKBENCH_WORKSPACE", r"F:\Video")).resolve()
        host = os.environ.get("PERIPHERAL_HOST", "127.0.0.1").strip().lower()
        if host not in _LOOPBACK_HOSTS:
            raise ValueError("PERIPHERAL_HOST must be a loopback host")

        state_root = workspace_root / "workspace-data"
        return cls(
            enabled=_read_bool("PERIPHERAL_ENABLED", default=False),
            host=host,
            port=_read_port("PERIPHERAL_PORT", default=8765),
            workspace_root=workspace_root,
            database_path=state_root / "peripheral.db",
            modules_root=state_root / "peripheral-modules",
            max_workers=1,
            poll_interval_seconds=0.25,
            shutdown_grace_seconds=10.0,
        )
