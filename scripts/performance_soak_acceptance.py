"""Run candidate-bound DP45 real-media soak, recovery and cleanup acceptance."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workbench.performance.soak_acceptance import run_soak_acceptance

from scripts.debug_program.candidate import validate_checkout
from scripts.debug_program.models import load_and_validate, validate_candidate_manifest


def _executable(value: str, name: str) -> str:
    path = Path(value).resolve()
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"{name} executable is required: {path}")
    return str(path)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path, default=Path("test-results/soak"))
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--ffprobe", required=True)
    parser.add_argument("--duration-seconds", type=float, required=True)
    parser.add_argument("--minimum-cycles", type=int, default=1)
    parser.add_argument("--cycle-interval-seconds", type=float, default=15.0)
    parser.add_argument("--page-count", type=int, default=2)
    parser.add_argument("--recovery-every", type=int, default=3)
    parser.add_argument("--cancellation-every", type=int, default=5)
    parser.add_argument("--ledger-segment-bytes", type=int, default=256 * 1024)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    candidate_path = args.candidate.resolve()
    candidate = load_and_validate(
        candidate_path, validate_candidate_manifest, candidate_path.parent
    )
    validate_checkout(candidate, repo_root)
    evidence = run_soak_acceptance(
        repo_root=repo_root,
        candidate=candidate,
        candidate_manifest_path=candidate_path,
        output_root=args.output_root,
        ffmpeg=_executable(args.ffmpeg, "ffmpeg"),
        ffprobe=_executable(args.ffprobe, "ffprobe"),
        duration_seconds=args.duration_seconds,
        minimum_cycles=args.minimum_cycles,
        cycle_interval_seconds=args.cycle_interval_seconds,
        page_count=args.page_count,
        recovery_every=args.recovery_every,
        cancellation_every=args.cancellation_every,
        ledger_segment_bytes=args.ledger_segment_bytes,
    )
    print(json.dumps({"status": "passed", "evidence": str(evidence)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
