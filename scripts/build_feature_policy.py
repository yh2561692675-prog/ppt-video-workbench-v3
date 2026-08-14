"""Bind the repository's safe feature policy to one release candidate."""

from __future__ import annotations

import argparse
from pathlib import Path

from workbench.release.feature_policy import (
    FeaturePolicy,
    default_feature_policy,
    load_feature_policy,
    write_feature_policy,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    args = parser.parse_args(argv)
    source = load_feature_policy(args.source) if args.source.is_file() else default_feature_policy()
    policy = source.model_copy(update={"candidate_id": args.candidate_id})
    # Re-validate after the candidate binding so malformed IDs cannot be
    # smuggled through model_copy.
    policy = FeaturePolicy.model_validate(policy.model_dump(mode="json"))
    write_feature_policy(args.output, policy)
    print(f"FEATURE_POLICY_WRITE=PASS candidate_id={args.candidate_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
