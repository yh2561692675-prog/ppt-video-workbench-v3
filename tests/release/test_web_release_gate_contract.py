from __future__ import annotations

from pathlib import Path


def test_web_release_gate_keeps_first_run_and_history_scenarios_separate() -> None:
    source = (Path(__file__).parents[2] / "scripts" / "run-web-release-gate.ps1").read_text(
        encoding="ascii"
    )

    assert "full-web-test" in source
    assert "web-typecheck" in source
    assert "web-build" in source
    assert "web-build-dist" in source
    assert "WorkflowShell.test.tsx" in source
    assert "$attempt -le 3" in source
    assert "WEB_RELEASE_GATE=PASS" in source
    assert "CandidateId" in source
