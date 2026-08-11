from __future__ import annotations

from workbench.providers.policy import local_first_policy, policy_fingerprint


def test_local_first_policy_is_deterministic_and_remote_fail_closed() -> None:
    left = local_first_policy(["builtin-llm", "builtin-asr", "builtin-llm"])
    right = local_first_policy(["builtin-asr", "builtin-llm"])
    assert left == right
    assert left.allow_remote_https is False
    assert left.allow_failover is False
    assert policy_fingerprint(left) == policy_fingerprint(right)


def test_empty_local_first_policy_does_not_write_provider_ids() -> None:
    policy = local_first_policy()
    assert policy.allowed_provider_ids is None
    assert policy_fingerprint(policy).startswith("sha256:")
