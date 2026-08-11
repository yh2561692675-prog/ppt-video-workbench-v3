from __future__ import annotations

import re
from pathlib import Path

from cloud_prototype.app import create_cloud_app

ROOT = Path(__file__).resolve().parents[2]


def test_cloud_openapi_references_resolve_to_declared_components() -> None:
    document = (ROOT / "schemas" / "cloud" / "cloud-collaboration-v1.openapi.yaml").read_text(
        encoding="utf-8"
    )
    assert "openapi: 3.1.0" in document
    references = set(
        re.findall(r"#/components/(?:schemas|responses|parameters|headers)/[A-Za-z0-9_]+", document)
    )
    declarations = set(
        match.group(1)
        for match in re.finditer(r"^    ([A-Za-z][A-Za-z0-9_]*):", document, re.MULTILINE)
    )
    missing = {
        reference
        for reference in references
        if reference.rsplit("/", 1)[-1] not in declarations
    }
    assert missing == set()


def test_cloud_openapi_documents_every_runtime_route(tmp_path: Path) -> None:
    document = (ROOT / "schemas" / "cloud" / "cloud-collaboration-v1.openapi.yaml").read_text(
        encoding="utf-8"
    )
    documented_routes: set[tuple[str, str]] = set()
    current_path: str | None = None
    for line in document.splitlines():
        path_match = re.match(r"^  (/[^:]+):\s*$", line)
        if path_match:
            current_path = path_match.group(1)
            continue
        operation_match = re.match(r"^    (get|post|put|patch|delete):\s*$", line)
        if current_path and operation_match:
            documented_routes.add((current_path, operation_match.group(1)))

    app = create_cloud_app(tmp_path / "control.db", tmp_path / "objects")
    runtime_routes = {
        (re.sub(r"\{[^}]+\}", "{}", route.path.removeprefix("/v1")), method.lower())
        for route in app.routes
        if getattr(route, "methods", None) and route.path.startswith("/v1/")
        for method in route.methods & {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }
    normalized_documented_routes = {
        (re.sub(r"\{[^}]+\}", "{}", path), method)
        for path, method in documented_routes
    }
    assert runtime_routes == normalized_documented_routes
