from __future__ import annotations

import argparse
from pathlib import Path

from workbench.release.manifest import (
    build_release_manifest,
    validate_runtime_manifest,
    write_runtime_manifest,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Write a hash-checked runtime manifest.")
    parser.add_argument("--release-root", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--api-executable", required=True, type=Path)
    parser.add_argument("--web-index", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--license-notice", required=True, type=Path)
    parser.add_argument("--sbom", required=True, type=Path)
    arguments = parser.parse_args(argv)

    manifest = build_release_manifest(
        arguments.release_root,
        api_executable=arguments.api_executable,
        web_index=arguments.web_index,
        runtime_root=arguments.runtime_root,
        license_paths=[arguments.license_notice],
        version=arguments.version,
    )
    manifest.sbom_relative_path = arguments.sbom.relative_to(arguments.release_root).as_posix()
    validation = validate_runtime_manifest(arguments.release_root, manifest)
    if not validation.valid:
        raise SystemExit(f"runtime manifest validation failed: {', '.join(validation.codes)}")
    write_runtime_manifest(arguments.release_root / "runtime-manifest.json", manifest)


if __name__ == "__main__":
    main()
