from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "tests" / "fixtures" / "effects" / "manifest.json"


def validate_manifest(path: Path = MANIFEST) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    pages = payload.get("pages", [])
    errors: list[str] = []
    if len(pages) != 40:
        errors.append(f"expected 40 pages, got {len(pages)}")
    categories = Counter(page.get("category") for page in pages)
    if len(categories) < 10 or any(count < 3 for count in categories.values()):
        errors.append("each of 10 categories must contain at least 3 pages")
    for page in pages:
        if set(page.get("aspect_ratios", [])) != {"16:9", "9:16"}:
            errors.append(f"{page.get('page_id')}: both aspect ratios are required")
        if page.get("checkpoints") != [0, 0.5, 1]:
            errors.append(f"{page.get('page_id')}: start/middle/end checkpoints are required")
    return {"pages": len(pages), "categories": dict(categories), "errors": errors}


def main() -> int:
    report = validate_manifest()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
