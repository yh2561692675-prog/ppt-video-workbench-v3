"""Create or freeze a clean-candidate performance-budget-v1 document."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    # ``python scripts/performance_budget.py`` is the documented Windows
    # operator entry point.  Add the repository root so sibling ``scripts``
    # modules resolve exactly as they do for ``python -m``.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workbench.performance.budget import (
    CandidateBindingV1,
    PerformanceBudgetV1,
    approve_budget,
    propose_budget,
    write_budget,
)

from scripts.debug_program.candidate import validate_checkout
from scripts.debug_program.models import load_and_validate, validate_candidate_manifest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _candidate_binding(candidate_path: Path, repo_root: Path) -> CandidateBindingV1:
    resolved = candidate_path.resolve()
    manifest = load_and_validate(resolved, validate_candidate_manifest, resolved.parent)
    validate_checkout(manifest, repo_root.resolve())
    return CandidateBindingV1(
        candidate_id=manifest["candidate_id"],
        source_commit=manifest["source"]["commit"],
        manifest_sha256=_sha256(resolved),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    propose = commands.add_parser("propose")
    propose.add_argument("--candidate", type=Path, required=True)
    propose.add_argument("--repo-root", type=Path, default=Path("."))
    propose.add_argument("--summary", type=Path, required=True)
    propose.add_argument("--events", type=Path, required=True)
    propose.add_argument("--fixture-id", required=True)
    propose.add_argument("--fixture-sha256", required=True)
    propose.add_argument(
        "--cache-mode", required=True, choices=("cold", "warm", "selective_invalidation")
    )
    propose.add_argument("--concurrency", required=True, type=int)
    propose.add_argument("--output", type=Path, required=True)
    freeze = commands.add_parser("freeze")
    freeze.add_argument("--candidate", type=Path, required=True)
    freeze.add_argument("--repo-root", type=Path, default=Path("."))
    freeze.add_argument("--input", type=Path, required=True)
    freeze.add_argument("--output", type=Path, required=True)
    freeze.add_argument("--reviewer", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    binding = _candidate_binding(args.candidate, args.repo_root)
    if args.command == "propose":
        budget = propose_budget(
            candidate=binding,
            fixture_id=args.fixture_id,
            fixture_sha256=args.fixture_sha256,
            cache_mode=args.cache_mode,
            concurrency=args.concurrency,
            summary_path=args.summary,
            events_path=args.events,
        )
        output = write_budget(args.output, budget)
    else:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        budget = PerformanceBudgetV1.model_validate(raw)
        if budget.candidate != binding:
            raise SystemExit("budget candidate binding does not match the clean checkout candidate")
        output = write_budget(args.output, approve_budget(budget, args.reviewer))
    written = PerformanceBudgetV1.model_validate_json(output.read_text(encoding="utf-8"))
    print(json.dumps({"budget": str(output), "status": written.status}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
