from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_candidate_identity import CandidateIdentityError, build_identity


def test_identity_binds_policy_and_records_source(tmp_path: Path) -> None:
    # The helper only needs a git checkout; use the real repository root in the
    # test suite so the source identity is the same one used by acceptance.
    repository_root = Path(__file__).parents[2]
    policy = repository_root / "schemas" / "feature-policy-default.json"
    assert policy.is_file()

    identity = build_identity(
        repository_root,
        candidate_id="rc-test",
        feature_policy_path=policy,
    )

    assert identity["source"]["git_commit"]
    assert identity["feature_policy"]["sha256"]
    assert identity["status"] in {"candidate_frozen", "candidate_blocked"}


def test_identity_rejects_invalid_candidate_id(tmp_path: Path) -> None:
    policy = tmp_path / "feature-policy.json"
    policy.write_text(json.dumps({"policy_id": "safe"}), encoding="utf-8")

    with pytest.raises(CandidateIdentityError, match="candidate_id_invalid"):
        build_identity(
            Path(__file__).parents[2],
            candidate_id="bad candidate",
            feature_policy_path=policy,
        )
