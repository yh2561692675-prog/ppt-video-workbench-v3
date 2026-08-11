from __future__ import annotations

import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))


def _manifest(path: Path, candidate_id: str = "rc-test-20260811") -> Path:
    path.write_text(json.dumps({"candidate_id": candidate_id}), encoding="utf-8")
    return path


def test_dry_run_writes_ordered_checkpoints_and_blocks_release(tmp_path: Path) -> None:
    from scripts.windows_acceptance.runner import execute
    from scripts.windows_acceptance_report import REQUIRED_PHASES

    status, report_path = execute(
        artifact_manifest=_manifest(tmp_path / "release-artifacts.json"),
        evidence_root=tmp_path / "evidence",
        run_id="run-a",
        dry_run=True,
    )

    report = json.loads(report_path.read_text(encoding="utf-8"))
    run_root = report_path.parents[1]
    assert status == 1
    assert report["decision"] == "block"
    assert (run_root / "checkpoints" / "artifact_resolution.started.json").is_file()
    assert (run_root / "checkpoints" / "clean_install.started.json").is_file()
    assert not (run_root / "checkpoints" / "first_launch.started.json").exists()
    assert list(REQUIRED_PHASES)[:2] == ["artifact_resolution", "clean_install"]


def test_resume_rejects_different_candidate_and_never_reuses_it(tmp_path: Path) -> None:
    from scripts.windows_acceptance.runner import AcceptanceRunError, execute

    execute(
        artifact_manifest=_manifest(tmp_path / "first.json", "rc-first"),
        evidence_root=tmp_path / "evidence",
        run_id="run-a",
        dry_run=True,
    )

    try:
        execute(
            artifact_manifest=_manifest(tmp_path / "second.json", "rc-second"),
            evidence_root=tmp_path / "evidence",
            run_id="ignored",
            resume_run_id="run-a",
            dry_run=True,
        )
    except AcceptanceRunError as error:
        assert str(error) == "resume_candidate_mismatch"
    else:
        raise AssertionError("cross-candidate resume must fail closed")
