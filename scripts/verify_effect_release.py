#!/usr/bin/env python3
"""Verify a release-candidate manifest without touching production data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from workbench.effects.rc_manifest import verify_rc_manifest  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--rc-manifest",
        type=Path,
        default=ROOT / "docs/effects/release-candidate-manifest.json",
    )
    args = parser.parse_args()
    result = verify_rc_manifest(args.rc_manifest, args.root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
