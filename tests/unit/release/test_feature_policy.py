from __future__ import annotations

import json
from pathlib import Path

import pytest
from workbench.release.feature_policy import (
    FeaturePolicy,
    FeaturePolicyError,
    load_feature_policy,
)


def test_safe_policy_keeps_legacy_and_new_projects_on_v1() -> None:
    policy = FeaturePolicy(policy_id="safe")

    assert policy.legacy_project_default == "v1"
    assert policy.new_project_default == "v1"
    assert policy.effects_v2.persistence is False
    assert policy.allow_fallback is True


def test_v2_default_requires_all_effect_capabilities() -> None:
    with pytest.raises(ValueError, match="all Effects V2 capabilities"):
        FeaturePolicy(
            policy_id="invalid",
            new_project_default="v2",
            effects_v2={"persistence": True, "preview": True, "render": False},
        )


def test_preview_cannot_be_enabled_without_persistence() -> None:
    with pytest.raises(ValueError, match="require persistence"):
        FeaturePolicy(policy_id="invalid", effects_v2={"preview": True})


def test_loader_rejects_malformed_policy(tmp_path: Path) -> None:
    path = tmp_path / "feature-policy.json"
    path.write_text(json.dumps({"schema_version": "broken"}), encoding="utf-8")

    with pytest.raises(FeaturePolicyError):
        load_feature_policy(path)
