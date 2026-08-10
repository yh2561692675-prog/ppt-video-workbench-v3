from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from peripheral_contracts import BusinessResultManifest, JobEnvelope

from workbench.business_modules.runtime import (
    BusinessExecution,
    StagedArtifact,
    business_input_fingerprint,
    execute_business_handler,
)


def build_package_manifest(root: Path, relative_paths: list[str]) -> dict[str, Any]:
    resolved_root = root.resolve()
    files: list[dict[str, Any]] = []
    for relative in sorted(relative_paths):
        target = (resolved_root / relative).resolve()
        if target.is_absolute() and not target.is_relative_to(resolved_root):
            raise ValueError("package file escapes project directory")
        if target.is_symlink() or not target.is_file():
            raise ValueError("package file must be a regular file")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        files.append(
            {
                "relative_path": target.relative_to(resolved_root).as_posix(),
                "size_bytes": target.stat().st_size,
                "sha256": digest,
            }
        )
    return {"files": files, "file_count": len(files)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    job = JobEnvelope.model_validate_json(args.request.read_text(encoding="utf-8"))

    def handler(received: JobEnvelope, attempt_root: Path) -> BusinessExecution:
        paths = received.parameters.get("relative_paths", [])
        if not isinstance(paths, list) or not all(isinstance(item, str) for item in paths):
            raise ValueError("relative_paths must be a list of strings")
        package = build_package_manifest(attempt_root, paths)
        output = attempt_root / "render.json"
        output.write_text(
            json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        fingerprint = business_input_fingerprint(received)
        result = BusinessResultManifest(
            schema_version="1.0",
            module_id="P11",
            job_type=received.job_type,
            project_id=received.project_id,
            project_revision=int(received.parameters.get("project_revision", 1)),
            input_fingerprint=fingerprint,
            cache_key=hashlib.sha256((fingerprint + "package_manifest").encode()).hexdigest(),
            result_type="package_manifest",
            payload=package,
        )
        return BusinessExecution(result, (StagedArtifact("render", "json", output),))

    execution = execute_business_handler(job, args.result.parent, args.result, "P11", handler)
    return 0 if execution.outcome == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
