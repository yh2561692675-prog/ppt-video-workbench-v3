from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("program_rc_manifest", ROOT / "scripts" / "build_program_rc_manifest.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_static_manifest_fails_closed_until_all_ordered_stop_points_exist() -> None:
    with pytest.raises(MODULE.RcManifestError, match="stop_points_missing"):
        MODULE.build_manifest(ROOT, candidate_id="rc-static-test")


def test_missing_stop_point_fails_closed(tmp_path: Path) -> None:
    points = tmp_path / "docs" / "acceptance" / "foundation" / "stop-points"
    points.mkdir(parents=True)
    (points / "a20.json").write_text('{"task":"A20","status":"ready","source_commit":"abc"}', encoding="utf-8")
    with pytest.raises(MODULE.RcManifestError, match="stop_points_missing"):
        MODULE._stop_points(tmp_path)
