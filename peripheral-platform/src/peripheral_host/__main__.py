from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from peripheral_contracts import JobEnvelope

from peripheral_host.api import create_internal_app
from peripheral_host.config import HostSettings
from peripheral_host.database import Database
from peripheral_host.logging_config import configure_logging
from peripheral_host.module_runner import ModuleRegistry, ModuleRunner, echo_registered_module
from peripheral_host.repositories import Repositories
from peripheral_host.scheduler import Scheduler
from peripheral_host.service import JobService


def _s1_job_environment_resolver(
    workspace_root: Path,
) -> Callable[[JobEnvelope], Mapping[str, str]]:
    def resolve(job: JobEnvelope) -> Mapping[str, str]:
        if job.job_type not in {"narration.generate", "audio.synthesize"}:
            return {}
        from uuid import UUID

        from workbench.settings.secret_store import WindowsDpapiProtector

        profile_value = job.parameters.get("profile_id")
        if not isinstance(profile_value, str):
            raise ValueError(f"{job.job_type} requires an opaque profile_id")
        profile_id = UUID(profile_value)
        if job.job_type == "narration.generate":
            from workbench.settings.secret_store import LlmProfileStore

            store = LlmProfileStore(
                workspace_root / "settings" / "llm-profiles.json", WindowsDpapiProtector()
            )
            credentials = store.credentials(profile_id)
            return {
                "WORKBENCH_LLM_PROFILE_ID": str(profile_id),
                "WORKBENCH_LLM_BASE_URL": str(credentials.profile.base_url).rstrip("/"),
                "WORKBENCH_LLM_API_KEY": credentials.api_key,
                "WORKBENCH_LLM_MODEL": credentials.profile.model,
            }
        from workbench.settings.heygen_store import HeyGenProfileStore

        heygen_store = HeyGenProfileStore(
            workspace_root / "settings" / "heygen-profiles.json", WindowsDpapiProtector()
        )
        heygen = heygen_store.credentials(profile_id)
        return {
            "WORKBENCH_HEYGEN_PROFILE_ID": str(profile_id),
            "WORKBENCH_HEYGEN_BASE_URL": str(heygen.profile.base_url).rstrip("/"),
            "WORKBENCH_HEYGEN_API_KEY": heygen.api_key,
        }

    return resolve


@dataclass(frozen=True, slots=True)
class HostRuntime:
    app: FastAPI
    scheduler: Scheduler
    database: Database


def build_runtime(settings: HostSettings) -> HostRuntime:
    database = Database(settings.database_path, _migrations_dir())
    database.initialize()
    repositories = Repositories(database)
    modules = [echo_registered_module()]
    if os.environ.get("PERIPHERAL_S1_MODULES", "").strip():
        from workbench.business_modules.registry import (
            business_registered_modules,
            enabled_module_ids,
        )

        modules.extend(business_registered_modules(enabled_module_ids()))
    registry = ModuleRegistry(modules)
    service = JobService(
        workspace_root=settings.workspace_root,
        repositories=repositories,
        registry=registry,
    )
    runner = ModuleRunner(
        registry,
        settings.workspace_root / "workspace-data" / "attempts",
        workspace_root=settings.workspace_root,
        job_environment_resolver=_s1_job_environment_resolver(settings.workspace_root),
    )
    scheduler = Scheduler(
        service=service,
        runner=runner,
        poll_interval_seconds=settings.poll_interval_seconds,
    )
    scheduler.recover_on_startup()
    return HostRuntime(
        app=create_internal_app(service=service, scheduler=scheduler),
        scheduler=scheduler,
        database=database,
    )


def main() -> None:
    configure_logging()
    settings = HostSettings.from_env()
    runtime = build_runtime(settings)
    runtime.scheduler.start()
    try:
        uvicorn.run(
            runtime.app,
            host=settings.host,
            port=settings.port,
            access_log=False,
            log_config=None,
        )
    finally:
        runtime.scheduler.stop(grace_seconds=settings.shutdown_grace_seconds)


def run_selected_module(arguments: list[str]) -> int | None:
    if not arguments or arguments[0] != "--run-module":
        return None
    if len(arguments) < 2:
        raise ValueError("missing bundled peripheral module")
    if arguments[1] == "echo":
        from peripheral_modules.echo.__main__ import main as module_main
    else:
        from workbench.business_modules.registry import module_main_for_id

        module_main = module_main_for_id(arguments[1])

    sys.argv = [sys.argv[0], *arguments[2:]]
    return module_main()


def _migrations_dir() -> Path:
    configured = os.environ.get("PERIPHERAL_MIGRATIONS_DIR")
    if configured:
        return Path(configured).resolve()
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root is not None:
        return Path(bundle_root, "migrations").resolve()
    return Path(__file__).resolve().parents[2] / "migrations"


if __name__ == "__main__":
    try:
        selected_exit_code = run_selected_module(sys.argv[1:])
        if selected_exit_code is None:
            main()
        else:
            raise SystemExit(selected_exit_code)
    except Exception:
        logging.getLogger(__name__).exception("peripheral host stopped during startup")
        raise
