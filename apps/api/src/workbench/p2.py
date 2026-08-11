"""Opt-in composition root for the P2 platform projects.

Flags default to disabled so existing local projects never create a network
client, cloud database, or new output path merely because this module exists.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

from workbench.platform.composition import create_platform_services
from workbench.platform.local import LocalPlatformServices
from workbench.providers.api import ProviderApiState, create_provider_router
from workbench.providers.registry import ProviderRegistry
from workbench.sync import SyncClient


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class P2FeatureFlags:
    provider_platform_enabled: bool = False
    platform_services_enabled: bool = False
    cloud_sync_enabled: bool = False

    @classmethod
    def from_environment(cls) -> P2FeatureFlags:
        return cls(
            provider_platform_enabled=_env_flag("PROVIDER_PLATFORM_ENABLED"),
            platform_services_enabled=_env_flag("PLATFORM_SERVICES_ENABLED"),
            cloud_sync_enabled=_env_flag("CLOUD_SYNC_ENABLED"),
        )


@dataclass
class P2Composition:
    flags: P2FeatureFlags
    platform: LocalPlatformServices | None = None
    provider_state: ProviderApiState | None = None
    sync_client: SyncClient | None = None

    @classmethod
    def build(
        cls,
        workspace_root: Path,
        *,
        app_version: str = "0.1.0",
        flags: P2FeatureFlags | None = None,
    ) -> P2Composition:
        configured = flags or P2FeatureFlags.from_environment()
        platform = (
            create_platform_services(workspace_root, app_version=app_version)
            if configured.platform_services_enabled
            else None
        )
        provider_state = (
            ProviderApiState(registry=ProviderRegistry([]), adapters={})
            if configured.provider_platform_enabled
            else None
        )
        sync_client = (
            SyncClient(workspace_root / ".sync" / "outbox.db", enabled=True)
            if configured.cloud_sync_enabled
            else None
        )
        return cls(
            configured,
            platform=platform,
            provider_state=provider_state,
            sync_client=sync_client,
        )

    def install(self, app: FastAPI) -> None:
        """Install only explicitly enabled local routes/state into an app."""

        app.state.p2_feature_flags = self.flags
        app.state.p2_platform_services = self.platform
        app.state.p2_provider_state = self.provider_state
        app.state.p2_sync_client = self.sync_client
        if self.provider_state is not None:
            app.include_router(create_provider_router(self.provider_state), prefix="/api")
