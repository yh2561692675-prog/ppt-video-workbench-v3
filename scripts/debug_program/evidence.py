"""Append-only evidence storage for scenario runs."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class EvidenceWriter:
    """Write evidence with create-new semantics; retries create new attempts."""

    def __init__(self, root: Path, candidate_id: str, run_id: str) -> None:
        self.root = root.resolve()
        self.candidate_id = candidate_id
        self.run_id = run_id
        self.run_root = self.root / candidate_id / run_id
        self.attempts_root = self.run_root / "attempts"
        self.attempts_root.mkdir(parents=True, exist_ok=True)

    def _create_json(self, path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = _canonical(value)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(path, flags)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def create_run(
        self,
        matrix: str,
        environment: dict[str, Any] | None = None,
        *,
        status: str = "planned",
    ) -> Path:
        if status not in {"planned", "running"}:
            raise ValueError("run must start as planned or running")
        path = self.run_root / "run.json"
        self._create_json(
            path,
            {
                "schema_version": "1.0",
                "run_id": self.run_id,
                "candidate_id": self.candidate_id,
                "matrix": matrix,
                "started_at": utc_now(),
                "attempt": 1,
                "status": status,
                "artifacts": [],
                "orphan_processes": [],
                "environment": environment or {},
            },
        )
        return path

    def start_attempt(self, scenario_id: str, attempt: int | None = None) -> tuple[str, Path]:
        number = attempt or 1
        while True:
            attempt_id = f"attempt-{number:03d}-{secrets.token_hex(3)}"
            path = self.attempts_root / attempt_id / "attempt.json"
            try:
                self._create_json(
                    path,
                    {
                        "scenario_id": scenario_id,
                        "attempt": number,
                        "started_at": utc_now(),
                        "status": "running",
                    },
                )
                return attempt_id, path.parent
            except FileExistsError:
                number += 1

    def finish_attempt(
        self,
        attempt_root: Path,
        *,
        status: str,
        artifacts: list[dict[str, Any]] | None = None,
        notes: list[str] | None = None,
    ) -> Path:
        if status not in {"passed", "failed", "blocked", "interrupted"}:
            raise ValueError("invalid attempt status")
        verdict = attempt_root / "verdict.json"
        self._create_json(
            verdict,
            {
                "schema_version": "1.0",
                "status": status,
                "finished_at": utc_now(),
                "artifacts": artifacts or [],
                "notes": notes or [],
            },
        )
        return verdict

    def recover_interrupted(self) -> list[Path]:
        recovered: list[Path] = []
        for attempt_root in sorted(self.attempts_root.glob("attempt-*")):
            if not attempt_root.is_dir() or (attempt_root / "verdict.json").exists():
                continue
            marker = attempt_root / "interrupted.json"
            with suppress(FileExistsError):
                self._create_json(
                    marker,
                    {
                        "status": "interrupted",
                        "detected_at": utc_now(),
                        "reason": "attempt has no terminal verdict",
                    },
                )
            recovered.append(marker)
        return recovered

    def manifest(self) -> Path:
        entries: list[dict[str, Any]] = []
        for path in sorted(self.run_root.rglob("*")):
            if path.is_file() and path.name != "evidence-manifest.json":
                entries.append(
                    {
                        "path": path.relative_to(self.run_root).as_posix(),
                        "size": path.stat().st_size,
                        "sha256": sha256_file(path),
                    }
                )
        output = self.run_root / "evidence-manifest.json"
        self._create_json(
            output,
            {
                "schema_version": "1.0",
                "candidate_id": self.candidate_id,
                "run_id": self.run_id,
                "generated_at": utc_now(),
                "files": entries,
            },
        )
        return output
