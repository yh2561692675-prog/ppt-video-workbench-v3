"""CLI for candidate validation, scenario discovery and evidence verdicts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .candidate import build_candidate, validate_checkout
from .evidence import EvidenceWriter
from .models import ValidationError, load_and_validate, validate_candidate_manifest, validate_run
from .registry import list_scenarios
from .runner import (
    full_automation_plan,
    new_run_id,
    python_smoke_plan,
    recover_automation,
    release_output_root,
    run_plan,
)


def _json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.debug_program")
    commands = parser.add_subparsers(dest="command", required=True)
    candidate = commands.add_parser("validate-candidate")
    candidate.add_argument("--candidate", required=True, type=Path)
    scenarios = commands.add_parser("list-scenarios")
    scenarios.add_argument("--matrix")
    scenarios.add_argument("--risk")
    scenarios.add_argument("--platform")
    scenarios.add_argument("--owner")
    scenarios.add_argument("--include-restricted", action="store_true")
    run = commands.add_parser("run")
    run.add_argument("--candidate", required=True, type=Path)
    run.add_argument("--matrix", default="local-e2e")
    run.add_argument("--evidence-root", type=Path, default=Path("test-results/debug-program"))
    run.add_argument("--repo-root", type=Path, default=Path("."))
    run.add_argument("--allow-external", action="store_true")
    automation = commands.add_parser("run-automation")
    automation.add_argument("--candidate", required=True, type=Path)
    automation.add_argument("--matrix", default="python-smoke")
    automation.add_argument(
        "--evidence-root", type=Path, default=Path("test-results/debug-program")
    )
    automation.add_argument("--repo-root", type=Path, default=Path("."))
    automation.add_argument(
        "--external-ci-evidence",
        type=Path,
        help="validated Windows/Ubuntu CI evidence required by dp20-full",
    )
    candidate_build = commands.add_parser("build-candidate")
    candidate_build.add_argument("--repo-root", type=Path, default=Path("."))
    candidate_build.add_argument(
        "--output-root", type=Path, default=Path("test-results/debug-program/candidates")
    )
    candidate_build.add_argument("--candidate-id")
    recover = commands.add_parser("recover-automation")
    recover.add_argument("--run", required=True, type=Path)
    verdict = commands.add_parser("verdict")
    verdict.add_argument("--run", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate-candidate":
            value = load_and_validate(
                args.candidate, validate_candidate_manifest, args.candidate.parent
            )
            _json({"valid": True, "candidate_id": value["candidate_id"]})
            return 0
        if args.command == "list-scenarios":
            _json(
                list_scenarios(
                    matrix=args.matrix,
                    risk=args.risk,
                    platform=args.platform,
                    owner=args.owner,
                    include_restricted=args.include_restricted,
                )
            )
            return 0
        if args.command == "run":
            candidate = load_and_validate(
                args.candidate, validate_candidate_manifest, args.candidate.parent
            )
            scenarios = list_scenarios(matrix=args.matrix, include_restricted=args.allow_external)
            if not scenarios:
                _json(
                    {
                        "status": "blocked_external_authorization",
                        "reason": "no authorized scenarios in matrix",
                    }
                )
                return 3
            validate_checkout(candidate, args.repo_root)
            run_id = new_run_id(candidate["candidate_id"], args.matrix)
            writer = EvidenceWriter(args.evidence_root, candidate["candidate_id"], run_id)
            writer.create_run(args.matrix)
            _json(
                {
                    "status": "planned",
                    "run_id": run_id,
                    "scenario_ids": [scenario["scenario_id"] for scenario in scenarios],
                }
            )
            return 0
        if args.command == "build-candidate":
            path = build_candidate(args.repo_root, args.output_root, args.candidate_id)
            _json({"candidate": str(path), "candidate_id": path.parent.name})
            return 0
        if args.command == "run-automation":
            candidate = load_and_validate(
                args.candidate, validate_candidate_manifest, args.candidate.parent
            )
            validate_checkout(candidate, args.repo_root)
            if args.matrix not in {"python-smoke", "dp20-full"}:
                raise ValidationError(f"unsupported automation matrix: {args.matrix}")
            run_id = new_run_id(candidate["candidate_id"], args.matrix)
            writer = EvidenceWriter(args.evidence_root, candidate["candidate_id"], run_id)
            release_root = release_output_root(
                args.repo_root.resolve(), candidate["candidate_id"], run_id
            )
            plan = (
                python_smoke_plan(args.repo_root.resolve())
                if args.matrix == "python-smoke"
                else full_automation_plan(
                    args.repo_root.resolve(),
                    args.candidate.resolve(),
                    release_output_root=release_root,
                    external_ci_evidence=args.external_ci_evidence,
                )
            )
            verdict = run_plan(
                writer=writer,
                matrix=args.matrix,
                commands=plan,
                environment={"runner": "scripts.debug_program.runner"},
            )
            _json(verdict)
            return 0 if verdict["status"] == "passed" else 1
        if args.command == "recover-automation":
            run_root = args.run.resolve()
            writer = EvidenceWriter(
                run_root.parents[1], run_root.parent.name, run_root.name
            )
            recovered = recover_automation(writer)
            _json({"status": "recovered" if recovered else "already_terminal"})
            return 0
        if args.command == "verdict":
            verdict_path = args.run / "automation-verdict.json"
            source = verdict_path if verdict_path.is_file() else args.run / "run.json"
            value = json.loads(source.read_text(encoding="utf-8"))
            if source.name == "run.json":
                validate_run(value)
            else:
                from .models import validate_automation_verdict

                validate_automation_verdict(value, args.run)
            _json(
                {
                    "status": value["status"],
                    "run_id": value["run_id"],
                    "candidate_id": value["candidate_id"],
                }
            )
            return 0
    except (ValidationError, OSError, json.JSONDecodeError) as exc:
        _json({"status": "invalid", "error": str(exc)})
        return 2
    return 2


if __name__ == "__main__":
    sys.exit(main())
