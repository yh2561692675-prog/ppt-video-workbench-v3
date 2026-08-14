from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("personal_use_preflight", ROOT / "scripts" / "personal_use_preflight.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_dirty_source_blocks_release_but_report_keeps_all_four_gates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MODULE, "git_output", lambda root, *args: "deadbeef" if args == ("rev-parse", "HEAD") else "dirty.txt")
    report = MODULE.build_report(tmp_path, candidate_id="rc-test", project_input=tmp_path / "sample.pptx", output_root=tmp_path / "out")
    assert set(report["gates"]) == {"source", "build", "runtime", "project"}
    assert report["status"] == "blocked"
    assert "source_worktree_dirty" in report["gates"]["source"]["reason_codes"]


def test_powerpoint_input_and_writable_output_can_pass_project_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sample = tmp_path / "sample.pptx"
    sample.write_bytes(b"ppt-fixture")
    monkeypatch.setattr(MODULE, "git_output", lambda root, *args: "a" * 40 if args == ("rev-parse", "HEAD") else "")
    monkeypatch.setattr(MODULE.shutil, "which", lambda name: f"C:/tools/{name}.exe")
    report = MODULE.build_report(tmp_path, candidate_id="rc-test", project_input=sample, output_root=tmp_path / "out")
    assert report["gates"]["project"]["status"] == "passed"
    assert report["gates"]["source"]["status"] == "passed"


def test_stale_report_when_candidate_or_input_changes() -> None:
    report = {"candidate_id": "rc-old", "source_commit": "a", "input_fingerprint": "b", "config_hash": "c"}
    current = {"candidate_id": "rc-new", "source_commit": "a", "input_fingerprint": "b", "config_hash": "c"}
    assert MODULE.is_stale(report, current)


def test_report_round_trips_as_json(tmp_path: Path) -> None:
    path = tmp_path / "preflight.json"
    value = {"schema_version": "1.0", "status": "blocked"}
    MODULE.write_report(path, value)
    assert json.loads(path.read_text(encoding="utf-8")) == value
