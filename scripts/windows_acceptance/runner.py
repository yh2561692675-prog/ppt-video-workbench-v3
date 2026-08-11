from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.windows_acceptance.evidence import phase_record, utc_now, write_json_atomic
from scripts.windows_acceptance_report import REQUIRED_PHASES, write_report


class AcceptanceRunError(RuntimeError):
    pass


def _read_candidate(manifest_path: Path) -> str:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        candidate_id = payload["candidate_id"]
    except (OSError, TypeError, ValueError, KeyError) as error:
        raise AcceptanceRunError("artifact_manifest_invalid") from error
    if not isinstance(candidate_id, str) or not candidate_id.strip():
        raise AcceptanceRunError("artifact_manifest_candidate_missing")
    return candidate_id


def _state_path(root: Path) -> Path:
    return root / "run-state.json"


def _load_or_create_state(
    root: Path, candidate_id: str, resume_run_id: str | None
) -> tuple[str, dict[str, Any]]:
    if resume_run_id:
        if root.name != resume_run_id:
            root = root.parent / resume_run_id
        path = _state_path(root)
        if not path.is_file():
            raise AcceptanceRunError("resume_run_not_found")
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("candidate_id") != candidate_id:
            raise AcceptanceRunError("resume_candidate_mismatch")
        return resume_run_id, state
    run_id = root.name
    state = {"schema_version": "1.0", "run_id": run_id, "candidate_id": candidate_id, "phases": {}}
    write_json_atomic(_state_path(root), state)
    return run_id, state


def execute(
    *,
    artifact_manifest: Path,
    evidence_root: Path,
    run_id: str,
    dry_run: bool,
    resume_run_id: str | None = None,
    fail_phase: str | None = None,
) -> tuple[int, Path]:
    """Run orchestration; PowerShell plugs real Windows actions into this shell."""
    if fail_phase is not None and fail_phase not in REQUIRED_PHASES:
        raise AcceptanceRunError("fail_phase_unknown")
    candidate_id = _read_candidate(artifact_manifest)
    run_root = evidence_root / (resume_run_id or run_id)
    run_root.mkdir(parents=True, exist_ok=True)
    run_id, state = _load_or_create_state(run_root, candidate_id, resume_run_id)
    phases: dict[str, Any] = state.setdefault("phases", {})

    for phase_name in REQUIRED_PHASES:
        prior = phases.get(phase_name)
        if isinstance(prior, dict) and prior.get("result") == "passed":
            continue
        started = utc_now()
        checkpoint = {"phase": phase_name, "status": "started", "started_at": started, "attempt": 1}
        write_json_atomic(run_root / "checkpoints" / f"{phase_name}.started.json", checkpoint)
        state["phases"] = phases
        write_json_atomic(_state_path(run_root), state)

        detail_path = run_root / "phase-evidence" / f"{phase_name}.json"
        result: str
        reasons: list[str]
        metrics: dict[str, object]
        if phase_name == "artifact_resolution":
            result, reasons, metrics = "passed", [], {"candidate_id": candidate_id}
        elif fail_phase == phase_name:
            result, reasons, metrics = "failed", ["simulated_failure"], {"mode": "test"}
        elif dry_run:
            result, reasons, metrics = (
                "blocked",
                ["dry_run_not_physical_acceptance"],
                {"mode": "dry_run"},
            )
        else:
            result, reasons, metrics = (
                "blocked",
                ["windows_action_not_executed"],
                {"mode": "orchestrator_only"},
            )
        write_json_atomic(
            detail_path,
            {"phase": phase_name, "result": result, "reason_codes": reasons},
        )
        finished = utc_now()
        phases[phase_name] = phase_record(
            result=result,
            started_at=started,
            finished_at=finished,
            attempt=1,
            reason_codes=reasons,
            evidence_refs=[detail_path.relative_to(run_root).as_posix()],
            metrics=metrics,
        )
        write_json_atomic(_state_path(run_root), state)
        if result != "passed":
            break

    evidence = {
        "schema_version": "2.0",
        "release": {
            "candidate_id": candidate_id,
            "artifact_manifest": artifact_manifest.name,
            "execution_mode": "dry_run" if dry_run else "orchestrator_only",
        },
        "phases": phases,
    }
    evidence_path = run_root / "acceptance-evidence.json"
    write_json_atomic(evidence_path, evidence)
    report_root = run_root / "report"
    status = write_report(evidence_path, report_root)
    return status, report_root / "acceptance-report.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-manifest", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--resume-run-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fail-phase")
    args = parser.parse_args(argv)
    try:
        status, report_path = execute(
            artifact_manifest=args.artifact_manifest,
            evidence_root=args.evidence_root,
            run_id=args.run_id,
            dry_run=args.dry_run,
            resume_run_id=args.resume_run_id,
            fail_phase=args.fail_phase,
        )
    except AcceptanceRunError as error:
        print(f"WINDOWS_FULL_CHAIN_ACCEPTANCE=BLOCK reason={error}")
        return 1
    decision = "PASS" if status == 0 else "BLOCK"
    print(f"WINDOWS_FULL_CHAIN_ACCEPTANCE={decision} report={report_path}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
