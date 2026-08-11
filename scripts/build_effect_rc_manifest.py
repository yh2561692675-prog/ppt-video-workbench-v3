#!/usr/bin/env python3
"""Build a deterministic RC manifest from an already-built installer."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api/src"))

from workbench.effects.rc_manifest import sha256_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--installer", type=Path, required=True)
    parser.add_argument("--rc-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assets = {
        "education_manifest": "fixtures/effects/education-v2/manifest.json",
        "ground_truth": "fixtures/effects/education-v2/ground-truth.json",
        "visual_review": "docs/effects/visual-review.json",
    }
    payload = {
        "rc_id": args.rc_id,
        "installer_sha256": sha256_file(args.installer),
        "assets": {name: sha256_file(args.root / rel) for name, rel in assets.items()},
        "v2_enabled": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
