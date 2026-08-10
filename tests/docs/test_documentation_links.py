from __future__ import annotations

import json
import re
from pathlib import Path

from workbench.domain.models import validate_manifest

REPOSITORY_ROOT = Path(__file__).parents[2]
DOCUMENTS = [
    REPOSITORY_ROOT / "docs" / "user-guide.md",
    REPOSITORY_ROOT / "docs" / "api-setup.md",
    REPOSITORY_ROOT / "docs" / "troubleshooting.md",
]
DEMO_ROOT = REPOSITORY_ROOT / "examples" / "demo-project"
MARKDOWN_LINK = re.compile(r"\[[^]]+\]\(([^)]+)\)")


def test_documentation_relative_links_resolve() -> None:
    for document in [*DOCUMENTS, DEMO_ROOT / "README.md"]:
        source = document.read_text(encoding="utf-8")
        for target in MARKDOWN_LINK.findall(source):
            if target.startswith(("http://", "https://", "#", "/api/")):
                continue
            assert (document.parent / target).resolve().is_file(), (document, target)


def test_demo_project_is_a_valid_synthetic_manifest() -> None:
    manifest_path = DEMO_ROOT / "project.json"
    manifest = validate_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))

    assert 6 <= len(manifest.pages) <= 8
    assert manifest.name == "星港数据安全入门演示"
    assert all(page.narration and page.narration.text for page in manifest.pages)
    assert all(
        page.narration and page.narration.source_refs == ["synthetic:demo"]
        for page in manifest.pages
    )


def test_docs_and_demo_have_no_credential_or_source_residue() -> None:
    files = [*DOCUMENTS, DEMO_ROOT / "README.md", DEMO_ROOT / "project.json"]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in files).lower()

    assert not re.search(r"\bsk-[a-z0-9]{12,}\b", combined)
    assert "authorization:" not in combined
    assert "bearer " not in combined
    assert "cookie:" not in combined
    assert "用户源文件" not in (DEMO_ROOT / "README.md").read_text(encoding="utf-8")
