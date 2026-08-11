"""Build an auditable ownership map from stop points and Git status."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from workbench.foundation.contracts import OwnershipEntryV1, OwnershipMapV1, WindowStopPointV1

_GENERATED_ROOTS = {
    ".pnpm-store": "cache",
    ".pytest_cache": "cache",
    ".ruff_cache": "cache",
    ".tmp": "cache",
    ".tmp-s1-frozen-smoke": "cache",
    ".tmp-s1-schema-probe": "cache",
    "backup": "backup",
    "cache": "cache",
    "installer": "generated",
    "release": "generated",
}


def _run_git(repo: Path) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.quotePath=false",
            "-C",
            str(repo),
            "status",
            "--porcelain=v2",
            "--untracked-files=all",
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def _status_paths(status: str) -> list[str]:
    paths: list[str] = []
    for line in status.splitlines():
        if line.startswith("? "):
            path = line[2:]
        elif line.startswith(("1 ", "2 ", "u ")):
            path = line.split("\t", 1)[-1] if "\t" in line else line.rsplit(" ", 1)[-1]
        else:
            continue
        path = path.replace("\\", "/").strip().rstrip("/")
        if "\t" in path:
            path = path.split("\t", 1)[0]
        if path:
            paths.append(path)
    return sorted(set(paths))


def _matches(path: str, pattern: str) -> bool:
    normalized = pattern.replace("\\", "/").rstrip("/")
    return (
        path == normalized
        or path.startswith(f"{normalized}/")
        or fnmatch.fnmatchcase(path, normalized)
        or PurePosixPath(path).match(normalized)
    )


def _generated_category(path: str) -> str | None:
    parts = path.split("/")
    root_category = _GENERATED_ROOTS.get(parts[0])
    if root_category is not None:
        return root_category
    if "__pycache__" in parts or path.endswith((".pyc", ".log", ".bak", ".zip")):
        return "generated"
    return None


def _load_stop_points(directory: Path) -> list[WindowStopPointV1]:
    points: list[WindowStopPointV1] = []
    for path in sorted(
        directory.glob("*.json"), key=lambda item: (item.stat().st_mtime_ns, item.name)
    ):
        payload = json.loads(path.read_text(encoding="utf-8"))
        # Some legacy stop points carry non-contract evidence metadata. Keep the
        # core contract strict while allowing the audit reader to consume it.
        payload.pop("evidence", None)
        points.append(WindowStopPointV1.model_validate(payload))
    return points


def _owner_key(window_id: str, task_name: str = "") -> str:
    """Group chronological Foundation stop points without merging other tasks."""

    base = window_id[:36] if len(window_id) >= 36 else window_id
    if task_name.startswith("Shared Foundation"):
        return f"{base}::shared-foundation"
    return f"{base}::{task_name}"


def build_map(repository: Path, stop_points_dir: Path) -> OwnershipMapV1:
    status = _run_git(repository)
    paths = _status_paths(status)
    points_by_owner: dict[str, WindowStopPointV1] = {}
    for point in _load_stop_points(stop_points_dir):
        points_by_owner[_owner_key(point.window_id, point.task_name)] = point
    points = list(points_by_owner.values())
    matches: dict[str, list[WindowStopPointV1]] = {}
    for path in paths:
        matches[path] = [
            point
            for point in points
            if any(_matches(path, pattern) for pattern in point.owned_paths)
        ]

    entries: list[OwnershipEntryV1] = []
    unknown_paths: list[str] = []
    semantic_conflicts: list[str] = []
    for path in paths:
        owners = matches[path]
        if not owners:
            generated_category = _generated_category(path)
            if generated_category is not None:
                entries.append(
                    OwnershipEntryV1(
                        path=path,
                        owner_window_id="foundation-generated",
                        category=generated_category,  # type: ignore[arg-type]
                        authority=False,
                    )
                )
                continue
            unknown_paths.append(path)
            continue
        if len(owners) > 1:
            semantic_conflicts.append(path)
            continue
        owner = owners[0]
        entries.append(
            OwnershipEntryV1(
                path=path,
                owner_window_id=owner.window_id,
                category="source",
                authority=owner.mode == "idle" and not owner.will_write_again,
            )
        )

    return OwnershipMapV1(
        schema_version="1.0",
        generated_at=datetime.now(UTC),
        entries=entries,
        unknown_paths=unknown_paths,
        semantic_conflicts=semantic_conflicts,
        source_status_manifest_sha256=hashlib.sha256(status.encode("utf-8")).hexdigest(),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--stop-points", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build_map(args.repository.resolve(), args.stop_points.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "unknown_paths": len(result.unknown_paths),
                "semantic_conflicts": len(result.semantic_conflicts),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
