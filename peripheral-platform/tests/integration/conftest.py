from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from peripheral_host.database import Database
from peripheral_host.module_runner import ModuleRegistry, ModuleRunner, echo_registered_module
from peripheral_host.repositories import Repositories
from peripheral_host.scheduler import Scheduler
from peripheral_host.service import JobService


class MutableClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current += timedelta(seconds=seconds)


@pytest.fixture
def migrations_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "migrations"


@pytest.fixture
def database(tmp_path: Path, migrations_dir: Path) -> Database:
    instance = Database(tmp_path / "peripheral.db", migrations_dir)
    instance.initialize()
    return instance


@pytest.fixture
def repositories(database: Database) -> Repositories:
    return Repositories(database)


@pytest.fixture
def scheduler_bundle(tmp_path: Path, migrations_dir: Path):
    workspace = tmp_path / "workspace"
    database = Database(workspace / "workspace-data" / "peripheral.db", migrations_dir)
    database.initialize()
    repositories = Repositories(database)
    registry = ModuleRegistry([echo_registered_module()])
    service = JobService(
        workspace_root=workspace,
        repositories=repositories,
        registry=registry,
    )
    clock = MutableClock(datetime(2026, 8, 8, 8, 0, tzinfo=UTC))
    runner = ModuleRunner(registry, workspace / "workspace-data" / "attempts")
    scheduler = Scheduler(service=service, runner=runner, clock=clock.now)
    return scheduler, service, repositories, clock
