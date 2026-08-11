"""Per-run workspace and resource isolation."""

from __future__ import annotations

import json
import os
import shutil
import socket
import tempfile
from pathlib import Path

from .evidence import utc_now


class IsolatedRun:
    """Own only resources created under one run root; never kill unknown PIDs."""

    def __init__(
        self, root: Path, candidate_id: str, run_id: str, requested_ports: int = 0
    ) -> None:
        self.root = root.resolve() / candidate_id / run_id
        self.candidate_id = candidate_id
        self.run_id = run_id
        self.requested_ports = requested_ports
        self.ports: list[int] = []
        self.workspace = self.root / "workspace"
        self.cache = self.root / "cache"
        self.browser_profile = self.root / "browser-profile"
        self.office_profile = self.root / "office-profile"
        self.artifacts = self.root / "artifacts"
        self._port_sockets: list[socket.socket] = []

    def __enter__(self) -> IsolatedRun:
        for path in (
            self.workspace,
            self.cache,
            self.browser_profile,
            self.office_profile,
            self.artifacts,
        ):
            path.mkdir(parents=True, exist_ok=False)
        for _ in range(self.requested_ports):
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("127.0.0.1", 0))
            self._port_sockets.append(sock)
            self.ports.append(int(sock.getsockname()[1]))
        self._write_environment("running")
        return self

    def _write_environment(self, status: str) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "environment.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "candidate_id": self.candidate_id,
                    "run_id": self.run_id,
                    "status": status,
                    "ports": self.ports,
                    "pid": os.getpid(),
                    "created_at": utc_now(),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def path(self, relative: str) -> Path:
        path = (self.root / relative).resolve()
        if self.root not in path.parents and path != self.root:
            raise ValueError("isolated path escapes run root")
        return path

    def __exit__(self, *_: object) -> None:
        for sock in self._port_sockets:
            sock.close()
        self._port_sockets.clear()
        self._write_environment("closed")

    def cleanup(self) -> None:
        """Remove only the caller-owned temporary run root."""
        if self.root.exists():
            shutil.rmtree(self.root)


def temp_run_root(prefix: str = "debug-program-") -> Path:
    return Path(tempfile.mkdtemp(prefix=prefix))
