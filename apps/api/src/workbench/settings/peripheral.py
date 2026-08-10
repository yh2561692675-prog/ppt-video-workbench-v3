from __future__ import annotations

import os
from dataclasses import dataclass


def _read_enabled() -> bool:
    raw_value = os.environ.get("PERIPHERAL_ENABLED", "false").strip().lower()
    if raw_value == "true":
        return True
    if raw_value == "false":
        return False
    raise ValueError("PERIPHERAL_ENABLED must be 'true' or 'false'")


@dataclass(frozen=True, slots=True)
class WorkbenchPeripheralSettings:
    enabled: bool = False
    base_url: str = "http://127.0.0.1:8765"
    timeout_seconds: float = 3.0

    @classmethod
    def from_env(cls) -> WorkbenchPeripheralSettings:
        host = os.environ.get("PERIPHERAL_HOST", "127.0.0.1").strip().lower()
        if host not in {"127.0.0.1", "localhost"}:
            raise ValueError("PERIPHERAL_HOST must be a loopback host")
        port = int(os.environ.get("PERIPHERAL_PORT", "8765"))
        if not 1 <= port <= 65535:
            raise ValueError("PERIPHERAL_PORT must be between 1 and 65535")
        timeout_seconds = float(os.environ.get("PERIPHERAL_TIMEOUT_SECONDS", "3.0"))
        if timeout_seconds <= 0:
            raise ValueError("PERIPHERAL_TIMEOUT_SECONDS must be positive")
        return cls(
            enabled=_read_enabled(),
            base_url=f"http://{host}:{port}",
            timeout_seconds=timeout_seconds,
        )
