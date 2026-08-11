"""Explicit P2 cache invalidation rules.

The legacy dependency graph describes project stages. This matrix describes
cross-platform/provider/cloud metadata changes, so callers can invalidate the
smallest artifact scope without deleting content caches on billing-only or
review-only changes.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

P2ChangeKind = Literal[
    "provider_price_changed",
    "provider_model_changed",
    "provider_adapter_changed",
    "provider_policy_changed",
    "platform_capability_changed",
    "runtime_changed",
    "font_changed",
    "cloud_revision_changed",
    "cloud_comment_changed",
    "cloud_review_changed",
    "input_changed",
]
P2ArtifactKind = Literal["content", "provider_result", "media", "renderer", "video", "final"]


@dataclass(frozen=True)
class P2CacheArtifact:
    name: str
    kind: P2ArtifactKind
    provider_kind: str | None = None


@dataclass(frozen=True)
class P2InvalidationDecision:
    artifact: str
    rebuild: bool
    reason: str


class P2InvalidationMatrix:
    """Keep P2 metadata changes precise and deterministic."""

    version = "p2-invalidation-v1"

    def decide(
        self,
        change: P2ChangeKind,
        artifact: P2CacheArtifact,
    ) -> P2InvalidationDecision:
        if change in {"provider_price_changed", "cloud_comment_changed", "cloud_review_changed"}:
            return P2InvalidationDecision(
                artifact.name,
                False,
                "metadata-only change preserves existing content and media artifacts",
            )

        if change in {
            "provider_model_changed",
            "provider_adapter_changed",
            "provider_policy_changed",
        }:
            rebuild = artifact.kind == "provider_result" or (
                artifact.kind == "renderer" and artifact.provider_kind == "renderer"
            ) or (
                artifact.kind == "media"
                and artifact.provider_kind in {"tts", "asr", "ocr", "avatar"}
            )
            return P2InvalidationDecision(
                artifact.name,
                rebuild,
                "provider execution identity or routing policy changed"
                if rebuild
                else "unrelated artifact does not depend on provider execution",
            )

        if change in {"platform_capability_changed", "runtime_changed", "font_changed"}:
            rebuild = artifact.kind in {"renderer", "media", "video", "final"}
            return P2InvalidationDecision(
                artifact.name,
                rebuild,
                "platform/runtime/font fingerprint changed"
                if rebuild
                else "platform metadata does not affect this artifact",
            )

        if change == "cloud_revision_changed":
            rebuild = artifact.kind in {
                "content",
                "provider_result",
                "renderer",
                "media",
                "video",
                "final",
            }
            return P2InvalidationDecision(
                artifact.name,
                rebuild,
                "cloud content revision changed" if rebuild else "artifact is not content-bound",
            )

        if change == "input_changed":
            rebuild = True
            return P2InvalidationDecision(
                artifact.name,
                rebuild,
                "input fingerprint changed",
            )

        raise ValueError(f"unsupported P2 invalidation change: {change}")

    def plan(
        self,
        change: P2ChangeKind,
        artifacts: Iterable[P2CacheArtifact],
    ) -> tuple[P2InvalidationDecision, ...]:
        return tuple(self.decide(change, artifact) for artifact in artifacts)
