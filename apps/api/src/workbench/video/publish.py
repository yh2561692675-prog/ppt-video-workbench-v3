from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PublishedRenderOutputs:
    mp4_path: Path
    package_path: Path
    latest_path: Path


def publish_render_outputs(
    *,
    staging_root: Path,
    output_root: Path,
    run_id: str,
    final_name: str,
    package_name: str,
) -> PublishedRenderOutputs:
    """Publish a completed render with an atomic stable-file cutover.

    The versioned package is immutable history. The stable MP4 and latest.json
    pointers are replaced only after all staged files have been copied.
    """

    staging_root = staging_root.resolve()
    output_root = output_root.resolve()
    staged_mp4 = _child_path(staging_root, final_name)
    staged_package = _child_path(staging_root, package_name)
    if not staged_mp4.is_file():
        raise FileNotFoundError(staged_mp4)
    if not staged_package.is_dir():
        raise FileNotFoundError(staged_package)

    output_root.mkdir(parents=True, exist_ok=True)
    stable_mp4 = output_root / final_name
    package_target = output_root / f"{package_name}-{run_id}"
    latest_path = output_root / "latest.json"

    temp_mp4 = output_root / f".{final_name}.{run_id}.tmp"
    shutil.copy2(staged_mp4, temp_mp4)
    os.replace(temp_mp4, stable_mp4)

    temp_package = output_root / f".{package_target.name}.tmp"
    if temp_package.exists():
        shutil.rmtree(temp_package)
    shutil.copytree(staged_package, temp_package)
    os.replace(temp_package, package_target)

    latest_payload = {
        "mp4_relative_path": stable_mp4.relative_to(output_root).as_posix(),
        "package_relative_path": package_target.relative_to(output_root).as_posix(),
        "run_id": run_id,
    }
    temp_latest = output_root / f".latest.{run_id}.tmp"
    temp_latest.write_text(
        json.dumps(latest_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temp_latest, latest_path)
    return PublishedRenderOutputs(
        mp4_path=stable_mp4,
        package_path=package_target,
        latest_path=latest_path,
    )


def _child_path(root: Path, name: str) -> Path:
    target = (root / name).resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path escapes root: {name}")
    return target
