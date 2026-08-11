"""Opt-in composition root for the P2 platform projects.

Flags default to disabled so existing local projects never create a network
client, cloud database, or new output path merely because this module exists.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI

from workbench.platform.composition import create_platform_services
from workbench.platform.credentials import PlatformCredentialStore, UnavailableCredentialBackend
from workbench.platform.local import LocalPlatformServices
from workbench.providers.adapter import ProviderAdapterError
from workbench.providers.api import ProviderApiState, create_provider_router
from workbench.providers.registry import ProviderRegistry
from workbench.providers.upstream import (
    BuiltinHandler,
    BuiltinProviderAdapter,
    builtin_descriptors,
)
from workbench.sync import SyncClient


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _not_configured(_: object) -> object:
    raise ProviderAdapterError(
        "provider.credentials_missing",
        "The built-in provider seam has not been configured",
        retryable=False,
        failover_allowed=False,
    )


def _redact_platform_paths(value: object) -> object:
    """Return diagnostics-safe metadata without host paths or secret values."""

    if isinstance(value, Mapping):
        return {
            key: (
                Path(str(item)).name
                if key == "executable_ref" and item is not None
                else _redact_platform_paths(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_platform_paths(item) for item in value]
    return value


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
        provider_handlers: dict[str, BuiltinHandler] | None = None,
    ) -> P2Composition:
        configured = flags or P2FeatureFlags.from_environment()
        platform = (
            create_platform_services(workspace_root, app_version=app_version)
            if configured.platform_services_enabled
            else None
        )
        provider_state = (
            ProviderApiState(
                registry=ProviderRegistry(builtin_descriptors()),
                adapters={
                    descriptor.provider_id: BuiltinProviderAdapter(
                        descriptor,
                        (provider_handlers or {}).get(descriptor.provider_id, _not_configured),
                    )
                    for descriptor in builtin_descriptors()
                },
                credential_store=(
                    platform.credentials
                    if platform is not None
                    else PlatformCredentialStore(UnavailableCredentialBackend())
                ),
            )
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

        if not any(self.flags.__dict__.values()):
            return

        @app.get("/api/p2/diagnostics", tags=["p2-platform"])
        def p2_diagnostics() -> dict[str, object]:
            """Return safe capability metadata; never return secrets or raw prompts."""

            platform_snapshot = (
                _redact_platform_paths(self.platform.capabilities().model_dump(mode="json"))
                if self.platform is not None
                else None
            )
            platform_details = (
                _redact_platform_paths({
                    "media": self.platform.media.snapshot(),
                    "office": self.platform.office.snapshot(),
                })
                if self.platform is not None
                else None
            )
            providers = (
                [item.model_dump(mode="json") for item in self.provider_state.registry.list()]
                if self.provider_state is not None
                else []
            )
            sync_state = self.sync_client.state().__dict__ if self.sync_client is not None else None
            return {
                "schema_version": 1,
                "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "flags": self.flags.__dict__,
                "platform": platform_snapshot,
                "platform_details": platform_details,
                "providers": providers,
                "sync": sync_state,
            }

        if self.provider_state is not None:
            app.include_router(create_provider_router(self.provider_state), prefix="/api")
