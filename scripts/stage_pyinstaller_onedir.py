from __future__ import annotations

import argparse
import shutil
from pathlib import Path

REQUIRED_RUNTIME_FILES = (
    Path("workbench.exe"),
    Path("_internal/python312.dll"),
    Path("_internal/vcruntime140.dll"),
    Path("_internal/vcruntime140_1.dll"),
    Path("_internal/msvcp140.dll"),
)


def _assert_complete_bundle(bundle_root: Path) -> None:
    missing = [path for path in REQUIRED_RUNTIME_FILES if not (bundle_root / path).is_file()]
    if missing:
        missing_text = ", ".join(path.as_posix() for path in missing)
        raise RuntimeError(f"PyInstaller onedir bundle is incomplete: {missing_text}")


def stage_onedir_bundle(source: Path, destination: Path) -> None:
    source = source.resolve()
    destination = destination.resolve()
    if source == destination:
        raise ValueError("Source and destination must be different directories.")

    _assert_complete_bundle(source)
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(child, target, dirs_exist_ok=True)
        else:
            shutil.copy2(child, target)
    _assert_complete_bundle(destination)

    shutil.rmtree(source)
    source_parent = source.parent
    if source_parent.is_dir() and not any(source_parent.iterdir()):
        source_parent.rmdir()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Promote a PyInstaller one-folder bundle into the release API directory."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    stage_onedir_bundle(args.source, args.destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
