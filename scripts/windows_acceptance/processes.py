from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class OwnedProcess:
    """A process is eligible for cleanup only when its run token matches."""

    pid: int
    run_id: str
    command_fingerprint: str


def cleanup_candidates(processes: Iterable[OwnedProcess], run_id: str) -> list[OwnedProcess]:
    return [process for process in processes if process.run_id == run_id and process.pid > 0]
