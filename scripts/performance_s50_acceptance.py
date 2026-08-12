"""Run DP43's isolated S50 real-media package and recovery acceptance."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workbench.performance.s50_acceptance import run_s50_acceptance

from scripts.debug_program.candidate import validate_checkout
from scripts.debug_program.models import load_and_validate, validate_candidate_manifest


def _executable(value: str | None, name: str) -> str:
    resolved = value or shutil.which(name)
    if not resolved:
        raise argparse.ArgumentTypeError(f"{name} executable is required")
    return resolved


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--output-root", type=Path, default=Path("test-results/performance-s50"))
    parser.add_argument("--ffmpeg")
    parser.add_argument("--ffprobe")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo_root = args.repo_root.resolve()
    candidate_path = args.candidate.resolve()
    candidate = load_and_validate(
        candidate_path, validate_candidate_manifest, candidate_path.parent
    )
    validate_checkout(candidate, repo_root)
    evidence = run_s50_acceptance(
        repo_root=repo_root,
        candidate=candidate,
        candidate_manifest_path=candidate_path,
        output_root=args.output_root,
        ffmpeg=_executable(args.ffmpeg, "ffmpeg"),
        ffprobe=_executable(args.ffprobe, "ffprobe"),
    )
    print(json.dumps({"status": "passed", "evidence": str(evidence)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
