"""CLI for candidate validation, scenario discovery and evidence verdicts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evidence import EvidenceWriter, utc_now
from .models import ValidationError, load_and_validate, validate_candidate_manifest, validate_run
from .registry import list_scenarios


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
    run.add_argument("--allow-external", action="store_true")
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
            timestamp = utc_now().replace("-", "").replace(":", "")
            run_id = f"{candidate['candidate_id']}-{args.matrix}-{timestamp}"
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
        if args.command == "verdict":
            value = json.loads((args.run / "run.json").read_text(encoding="utf-8"))
            validate_run(value)
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
