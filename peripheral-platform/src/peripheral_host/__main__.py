from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from peripheral_host.api import create_internal_app
from peripheral_host.config import HostSettings
from peripheral_host.database import Database
from peripheral_host.logging_config import configure_logging
from peripheral_host.module_runner import ModuleRegistry, ModuleRunner, echo_registered_module
from peripheral_host.repositories import Repositories
from peripheral_host.scheduler import Scheduler
from peripheral_host.service import JobService


@dataclass(frozen=True, slots=True)
class HostRuntime:
    app: FastAPI
    scheduler: Scheduler
    database: Database


def build_runtime(settings: HostSettings) -> HostRuntime:
    database = Database(settings.database_path, _migrations_dir())
    database.initialize()
    repositories = Repositories(database)
    registry = ModuleRegistry([echo_registered_module()])
    service = JobService(
        workspace_root=settings.workspace_root,
        repositories=repositories,
        registry=registry,
    )
    runner = ModuleRunner(registry, settings.workspace_root / "workspace-data" / "attempts")
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
    if len(arguments) < 2 or arguments[1] != "echo":
        raise ValueError("unknown bundled peripheral module")
    from peripheral_modules.echo.__main__ import main as echo_main

    sys.argv = [sys.argv[0], *arguments[2:]]
    return echo_main()


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
