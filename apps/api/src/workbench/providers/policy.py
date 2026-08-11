"""Deterministic provider policy filtering and safe failover decisions."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from workbench.contracts.p2_platform import _ContractModel, canonical_sha256

from .models import ProviderDescriptorV1

DataClassification = Literal["public", "internal", "sensitive", "restricted"]


class ProviderPolicyV1(_ContractModel):
    schema_version: int = 1
    allowed_provider_ids: list[str] | None = Field(default=None, max_length=100)
    fixed_provider_id: str | None = None
    allowed_regions: list[str] = Field(default_factory=list, max_length=100)
    max_data_classification: DataClassification = "sensitive"
    allow_remote_https: bool = False
    allow_failover: bool = True
    max_cost_minor: int | None = Field(default=None, ge=0)
    quality_floor: Literal["draft", "standard", "high"] = "standard"


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    provider_id: str
    reasons: tuple[str, ...]


class ProviderPolicyEvaluator:
    def __init__(self, policy: ProviderPolicyV1) -> None:
        self.policy = policy

    def evaluate(
        self,
        descriptor: ProviderDescriptorV1,
        *,
        data_classification: DataClassification,
        region: str | None = None,
    ) -> PolicyDecision:
        reasons: list[str] = []
        if (
            self.policy.allowed_provider_ids is not None
            and descriptor.provider_id not in self.policy.allowed_provider_ids
        ):
            reasons.append("provider_not_allowlisted")
        if (
            self.policy.fixed_provider_id is not None
            and descriptor.provider_id != self.policy.fixed_provider_id
        ):
            reasons.append("provider_not_fixed_choice")
        if descriptor.execution_mode == "remote_https" and not self.policy.allow_remote_https:
            reasons.append("remote_provider_disabled")
        if self.policy.allowed_regions and region not in self.policy.allowed_regions:
            reasons.append("region_not_allowed")
        if self._classification_rank(data_classification) > self._classification_rank(
            self.policy.max_data_classification
        ):
            reasons.append("data_classification_not_allowed")
        return PolicyDecision(not reasons, descriptor.provider_id, tuple(reasons))

    def filter(
        self,
        descriptors: list[ProviderDescriptorV1],
        *,
        data_classification: DataClassification,
        region: str | None = None,
    ) -> list[ProviderDescriptorV1]:
        return [
            descriptor
            for descriptor in descriptors
            if self.evaluate(
                descriptor, data_classification=data_classification, region=region
            ).allowed
        ]

    @staticmethod
    def _classification_rank(value: DataClassification) -> int:
        return {"public": 0, "internal": 1, "sensitive": 2, "restricted": 3}[value]


def local_first_policy(provider_ids: Iterable[str] = ()) -> ProviderPolicyV1:
    """Build a deterministic additive policy for legacy local projects.

    The policy is returned to the caller and is never written into a project
    manifest implicitly. Remote HTTPS is disabled and failover is conservative;
    an explicit project or organization policy can opt into a broader route.
    """

    normalized = sorted(
        {provider_id.strip() for provider_id in provider_ids if provider_id.strip()}
    )
    return ProviderPolicyV1(
        allowed_provider_ids=normalized or None,
        allow_remote_https=False,
        allow_failover=False,
    )


def policy_fingerprint(policy: ProviderPolicyV1) -> str:
    """Return the stable policy identity used by diagnostics and cache keys."""

    return canonical_sha256(policy.model_dump(mode="json"))


def failover_allowed(
    *,
    policy: ProviderPolicyV1,
    error_code: str,
    error_retryable: bool,
    billed_state: Literal["none", "known", "unknown"],
    fixed_provider: bool,
    region_would_expand: bool,
    budget_would_increase: bool,
) -> bool:
    """Central failover matrix; unknown paid state and policy expansion always block."""

    if fixed_provider or not policy.allow_failover or not error_retryable:
        return False
    if billed_state == "unknown" or region_would_expand or budget_would_increase:
        return False
    return error_code not in {"validation", "schema_mismatch", "credential_invalid", "manual_lock"}
