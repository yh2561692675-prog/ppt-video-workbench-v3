from __future__ import annotations

import re
from pathlib import Path

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
