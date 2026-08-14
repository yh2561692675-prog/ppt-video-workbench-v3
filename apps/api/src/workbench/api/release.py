from __future__ import annotations

import os

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from workbench.api.projects import Envelope, envelope
from workbench.release.feature_policy import FeaturePolicy


class ReleaseStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str | None
    source_commit: str | None
    feature_policy: FeaturePolicy


def create_release_router(policy: FeaturePolicy) -> APIRouter:
    router = APIRouter(prefix="/api/release")

    @router.get("/feature-policy", response_model=Envelope[FeaturePolicy])
    def feature_policy() -> Envelope[FeaturePolicy]:
        return envelope(policy)

    @router.get("/status", response_model=Envelope[ReleaseStatus])
    def release_status() -> Envelope[ReleaseStatus]:
        return envelope(
            ReleaseStatus(
                candidate_id=policy.candidate_id or os.environ.get("WORKBENCH_CANDIDATE_ID"),
                source_commit=os.environ.get("WORKBENCH_SOURCE_COMMIT") or None,
                feature_policy=policy,
            )
        )

    return router
