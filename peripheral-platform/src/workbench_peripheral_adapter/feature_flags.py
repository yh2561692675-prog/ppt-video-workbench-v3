from __future__ import annotations

from typing import Protocol

from workbench_peripheral_adapter.client import (
    DisabledPeripheralClient,
    HttpPeripheralClient,
    PeripheralClientProtocol,
)


class PeripheralSettingsProtocol(Protocol):
    @property
    def enabled(self) -> bool: ...

    @property
    def base_url(self) -> str: ...

    @property
    def timeout_seconds(self) -> float: ...


def create_peripheral_client(
    settings: PeripheralSettingsProtocol,
) -> PeripheralClientProtocol:
    if not settings.enabled:
        return DisabledPeripheralClient()
    return HttpPeripheralClient(
        settings.base_url,
        timeout_seconds=settings.timeout_seconds,
    )
