from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "scripts" / "foundation" / "build_ownership_map.py"
SPEC = importlib.util.spec_from_file_location("build_ownership_map", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_status_paths_support_untracked_and_porcelain_v2_records() -> None:
    status = "\n".join(
        [
            "1 .M N... 100644 100644 100644 a a apps/api/src/workbench/foundation/contracts.py",
            "? docs/acceptance/foundation/new.json",
            "u UU N... 100644 100644 100644 100644 a a a a tests/conflict.py",
        ]
    )
    assert MODULE._status_paths(status) == [
        "apps/api/src/workbench/foundation/contracts.py",
        "docs/acceptance/foundation/new.json",
        "tests/conflict.py",
    ]


@pytest.mark.parametrize(
    ("path", "pattern", "expected"),
    [
        (
            "apps/api/src/workbench/foundation/contracts.py",
            "apps/api/src/workbench/foundation",
            True,
        ),
        ("tests/unit/foundation/test.py", "tests/unit/foundation", True),
        ("docs/other.md", "docs/acceptance/foundation", False),
    ],
)
def test_owned_path_matching_is_contained(path: str, pattern: str, expected: bool) -> None:
    assert MODULE._matches(path, pattern) is expected


@pytest.mark.parametrize(
    ("path", "category"),
    [
        (".tmp/render/output.mp4", "cache"),
        ("backup/old.json", "backup"),
        ("apps/api/src/workbench/__pycache__/module.pyc", "generated"),
        ("apps/api/src/workbench/video/render_service.py", None),
    ],
)
def test_generated_artifact_classification_is_conservative(path: str, category: str | None) -> None:
    assert MODULE._generated_category(path) == category


def test_stop_points_from_one_window_share_an_owner_key() -> None:
    base = "019feb46-8950-7213-b4ca-422988a6b032"
    assert MODULE._owner_key(base + "-phase2") == base
    assert MODULE._owner_key(base + "-contracts") == base
    assert MODULE._owner_key("another-window") == "another-window"
