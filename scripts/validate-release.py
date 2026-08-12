from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path


def _toml_version(path: Path) -> str:
    with path.open("rb") as handle:
        return str(tomllib.load(handle)["project"]["version"])


def _json_version(path: Path) -> str:
    return str(json.loads(path.read_text(encoding="utf-8"))["version"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate an immutable source release.")
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    expected = args.version
    observed = {
        Path("pyproject.toml"): _toml_version(Path("pyproject.toml")),
        Path("apps/api/pyproject.toml"): _toml_version(Path("apps/api/pyproject.toml")),
        Path("package.json"): _json_version(Path("package.json")),
        Path("apps/web/package.json"): _json_version(Path("apps/web/package.json")),
    }
    mismatches = {
        path.as_posix(): version for path, version in observed.items() if version != expected
    }
    if mismatches:
        details = ", ".join(f"{path}={version}" for path, version in mismatches.items())
        raise SystemExit(f"release version {expected} does not match: {details}")

    notes = Path("docs/releases") / f"v{expected}.md"
    if not notes.is_file() or not notes.read_text(encoding="utf-8").strip():
        raise SystemExit(f"release notes are missing or empty: {notes}")
    print(f"validated release v{expected} using {notes}")


if __name__ == "__main__":
    main()
