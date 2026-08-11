from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from peripheral_contracts.business_results import BusinessResultManifest
from peripheral_contracts.models import (
    ArtifactManifest,
    EventEnvelope,
    JobEnvelope,
    JobResult,
    ModuleManifest,
)

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "job-envelope-1.0.json": JobEnvelope,
    "event-envelope-1.0.json": EventEnvelope,
    "artifact-manifest-1.0.json": ArtifactManifest,
    "job-result-1.0.json": JobResult,
    "module-manifest-1.0.json": ModuleManifest,
    "business-result-1.0.json": BusinessResultManifest,
}


def write_schema_snapshots(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMA_MODELS.items():
        payload = json.dumps(
            model.model_json_schema(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        (destination / filename).write_text(payload + "\n", encoding="utf-8", newline="\n")
