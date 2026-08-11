from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def phase_record(
    *,
    result: str,
    started_at: str,
    finished_at: str,
    attempt: int,
    reason_codes: list[str],
    evidence_refs: list[str],
    metrics: dict[str, object],
) -> dict[str, object]:
    started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    return {
        "result": result,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_ms": max(0, round((finished - started).total_seconds() * 1_000)),
        "attempt": attempt,
        "reason_codes": reason_codes,
        "evidence_refs": evidence_refs,
        "metrics": metrics,
    }
