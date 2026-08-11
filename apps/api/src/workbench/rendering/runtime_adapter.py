from __future__ import annotations

from collections.abc import Callable

from workbench.domain.enums import JobType
from workbench.domain.models import JobRecord
from workbench.jobs.registry import JobExecutorRegistry


def register_render_release_executor(
    registry: JobExecutorRegistry,
    handler: Callable[[JobRecord], None],
) -> None:
    """Register the B-line executor without replacing A's frozen registry entries."""

    registry.register(JobType.EXPORT_PACKAGE, handler)


__all__ = ["register_render_release_executor"]
