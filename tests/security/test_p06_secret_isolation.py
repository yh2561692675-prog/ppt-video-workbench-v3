from __future__ import annotations

import os
from uuid import uuid4


def test_p06_consumes_secret_environment_without_putting_it_in_parameters(monkeypatch) -> None:
    from workbench.business_modules.p06_narration.runner import (
        _consume_llm_environment,
        safe_parameters,
    )

    profile_id = uuid4()
    secret = "p06-test-secret-that-must-not-survive"
    monkeypatch.setenv("WORKBENCH_LLM_PROFILE_ID", str(profile_id))
    monkeypatch.setenv("WORKBENCH_LLM_BASE_URL", "https://llm.invalid/v1")
    monkeypatch.setenv("WORKBENCH_LLM_API_KEY", secret)
    monkeypatch.setenv("WORKBENCH_LLM_MODEL", "fake-model")

    resolved = _consume_llm_environment(profile_id)

    assert resolved[2] == secret
    assert "WORKBENCH_LLM_API_KEY" not in os.environ
    assert secret not in str(safe_parameters({"profile_id": str(profile_id)}))


def test_host_redacts_exact_ephemeral_secret_from_child_output() -> None:
    from peripheral_host.module_runner import _redact_output

    secret = "p06-child-secret"
    assert secret not in _redact_output(f"provider failed: {secret}", (secret,))
