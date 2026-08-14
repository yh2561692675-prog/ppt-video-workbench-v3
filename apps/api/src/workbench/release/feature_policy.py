"""Candidate-bound feature policy for personal-use releases.

The policy is deliberately separate from environment feature flags.  It is a
small, hashable contract that can be shipped with a release and exposed by a
read-only API endpoint.  A release can therefore prove which project defaults
and Effects V2 capabilities were intended for that exact candidate.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FeaturePolicyError(ValueError):
    """Raised when a feature policy is missing, malformed, or unsafe."""


class EffectsV2Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    persistence: bool = False
    preview: bool = False
    render: bool = False


class FeaturePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    policy_id: str = Field(min_length=1, max_length=120)
    candidate_id: str | None = None
    legacy_project_default: Literal["v1"] = "v1"
    new_project_default: Literal["v1", "v2"] = "v1"
    effects_v2: EffectsV2Policy = Field(default_factory=EffectsV2Policy)
    allow_fallback: bool = True
    status: Literal["candidate", "acceptance", "promotable"] = "candidate"

    @model_validator(mode="after")
    def validate_policy(self) -> FeaturePolicy:
        if self.candidate_id is not None and not re.fullmatch(
            r"rc-[A-Za-z0-9][A-Za-z0-9._-]*", self.candidate_id
        ):
            raise ValueError("candidate_id must use the rc- prefix")
        if (self.effects_v2.preview or self.effects_v2.render) and not self.effects_v2.persistence:
            raise ValueError("Effects V2 preview/render require persistence")
        if self.new_project_default == "v2" and not all(
            (
                self.effects_v2.persistence,
                self.effects_v2.preview,
                self.effects_v2.render,
            )
        ):
            raise ValueError("new_project_default=v2 requires all Effects V2 capabilities")
        if self.status == "promotable" and self.new_project_default != "v2":
            raise ValueError("promotable policy must select the V2 default")
        return self


def default_feature_policy(*, candidate_id: str | None = None) -> FeaturePolicy:
    """Return the fail-safe policy used when no packaged policy is present."""

    return FeaturePolicy(
        policy_id="effects-v1-safe-default",
        candidate_id=candidate_id,
    )


def load_feature_policy(path: Path) -> FeaturePolicy:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise FeaturePolicyError(f"feature_policy_invalid:{path}") from error
    if not isinstance(payload, dict):
        raise FeaturePolicyError("feature_policy_object_required")
    try:
        return FeaturePolicy.model_validate(payload)
    except ValueError as error:
        raise FeaturePolicyError("feature_policy_schema_invalid") from error


def write_feature_policy(path: Path, policy: FeaturePolicy) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(
            policy.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_environment_feature_policy() -> FeaturePolicy:
    candidate_id = os.environ.get("WORKBENCH_CANDIDATE_ID") or None
    configured_path = os.environ.get("WORKBENCH_FEATURE_POLICY")
    if not configured_path:
        return default_feature_policy(candidate_id=candidate_id)
    try:
        policy = load_feature_policy(Path(configured_path))
    except FeaturePolicyError:
        return default_feature_policy(candidate_id=candidate_id)
    if candidate_id and policy.candidate_id not in (None, candidate_id):
        return default_feature_policy(candidate_id=candidate_id)
    if candidate_id and policy.candidate_id is None:
        policy = policy.model_copy(update={"candidate_id": candidate_id})
    return policy
