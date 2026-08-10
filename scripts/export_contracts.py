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


if __name__ == "__main__":
    write_json(ROOT / "packages/contracts/project.schema.json", ProjectManifest.model_json_schema())
    write_json(ROOT / "packages/contracts/openapi.json", create_app().openapi())
