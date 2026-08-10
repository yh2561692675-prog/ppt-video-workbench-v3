from __future__ import annotations

import argparse
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

REQUIRED_FILES = frozenset(
    {
        "installer/workbench.iss",
        "scripts/build-release.ps1",
        "scripts/prepare-runtime.ps1",
    }
)
EXCLUDED_TOP_LEVEL = frozenset(
    {".git", ".venv", ".worktrees", "dist", "node_modules", "runtime-assets"}
)
EXCLUDED_FILENAMES = frozenset({".env"})


def source_files(repository_root: Path) -> list[Path]:
    try:
        completed = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            cwd=repository_root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        # A source checkout may be copied without its Git worktree metadata.
        # Fall back to the same inclusion policy over the filesystem so the
        # updater remains usable and still excludes generated/runtime payloads.
        paths = [
            path.relative_to(repository_root)
            for path in repository_root.rglob("*")
            if path.is_file()
        ]
    else:
        paths = [Path(name) for name in completed.stdout.decode("utf-8").split("\0") if name]
    return [path for path in paths if should_include(path)]


def should_include(path: Path) -> bool:
    parts = PurePosixPath(path.as_posix()).parts
    return (
        bool(parts)
        and parts[0] not in EXCLUDED_TOP_LEVEL
        and path.name not in EXCLUDED_FILENAMES
    )


def build_archive(repository_root: Path, output: Path) -> None:
    files = source_files(repository_root)
    relative_paths = {path.as_posix() for path in files}
    missing = REQUIRED_FILES - relative_paths
    if missing:
        raise RuntimeError(f"Source update is missing required files: {', '.join(sorted(missing))}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative_path in files:
            archive.write(repository_root / relative_path, relative_path.as_posix())


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a complete, safe source update archive.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository_root = Path(__file__).resolve().parents[1]
    build_archive(repository_root, args.output.resolve())
    print(f"Source update archive created: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
