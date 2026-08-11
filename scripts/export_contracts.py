import argparse
import json
from pathlib import Path

from workbench.domain.models import ProjectManifest
from workbench.main import create_app

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export the authoritative project schema and OpenAPI"
    )
    parser.add_argument("--check", action="store_true", help="fail when generated files drift")
    args = parser.parse_args()
    outputs = {
        ROOT / "packages/contracts/project.schema.json": ProjectManifest.model_json_schema(),
        ROOT / "packages/contracts/openapi.json": create_app().openapi(),
    }
    if args.check:
        drift = []
        for path, payload in outputs.items():
            expected = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                drift.append(str(path.relative_to(ROOT)))
        if drift:
            print("generated contract drift: " + ", ".join(drift))
            return 1
        print("verified project schema and OpenAPI")
        return 0
    for path, payload in outputs.items():
        write_json(path, payload)
    print("generated project schema and OpenAPI")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
