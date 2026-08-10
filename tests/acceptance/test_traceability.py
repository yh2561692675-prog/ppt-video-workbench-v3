from __future__ import annotations

import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).parents[2]
MANIFEST_PATH = ROOT / "tests" / "acceptance" / "fixtures-manifest.json"
TRACEABILITY_PATH = ROOT / "docs" / "traceability.xlsx"


def test_requirements_and_fixtures_are_complete() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    requirements = manifest["requirements"]
    expected = {
        *(f"FR-{index:03d}" for index in range(1, 17)),
        *(f"NFR-{index:03d}" for index in range(1, 8)),
    }

    assert {item["id"] for item in requirements} == expected
    assert all(item["test_ids"] and item["evidence"] for item in requirements)
    assert len({test_id for item in requirements for test_id in item["test_ids"]}) >= 16

    fixture_kinds = {fixture["kind"] for fixture in manifest["fixtures"]}
    assert {
        "pptx",
        "pdf-searchable",
        "pdf-scanned",
        "jpg",
        "png",
        "webp",
        "bmp",
        "tiff-multipage",
        "audio-wav",
        "heygen-fake",
        "corrupt-file",
        "interrupted-job",
    } <= fixture_kinds
    assert all(
        fixture["execution"] in {"linux_automated", "windows_manual"}
        for fixture in manifest["fixtures"]
    )


def test_traceability_workbook_contains_named_sheets() -> None:
    assert TRACEABILITY_PATH.is_file()
    with zipfile.ZipFile(TRACEABILITY_PATH) as workbook:
        names = workbook.read("xl/workbook.xml").decode("utf-8")

    assert "Summary" in names
    assert "Traceability" in names
    assert "Fixtures" in names
