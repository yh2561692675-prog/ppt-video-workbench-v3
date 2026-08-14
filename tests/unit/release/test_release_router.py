from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from workbench.api.release import create_release_router
from workbench.release.feature_policy import FeaturePolicy


def test_release_router_exposes_candidate_bound_policy() -> None:
    app = FastAPI()
    app.include_router(
        create_release_router(FeaturePolicy(policy_id="safe", candidate_id="rc-test"))
    )

    with TestClient(app) as client:
        policy = client.get("/api/release/feature-policy")
        status = client.get("/api/release/status")

    assert policy.status_code == 200
    assert policy.json()["data"]["candidate_id"] == "rc-test"
    assert status.status_code == 200
    assert status.json()["data"]["feature_policy"]["policy_id"] == "safe"
