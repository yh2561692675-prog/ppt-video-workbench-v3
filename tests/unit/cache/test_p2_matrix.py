from __future__ import annotations

from workbench.cache.p2_matrix import P2CacheArtifact, P2InvalidationMatrix


def _artifacts() -> list[P2CacheArtifact]:
    return [
        P2CacheArtifact("source", "content"),
        P2CacheArtifact("llm", "provider_result", "llm"),
        P2CacheArtifact("tts", "media", "tts"),
        P2CacheArtifact("render", "renderer", "renderer"),
        P2CacheArtifact("video", "video"),
        P2CacheArtifact("final", "final"),
    ]


def test_price_comments_and_reviews_preserve_all_artifacts() -> None:
    matrix = P2InvalidationMatrix()
    for change in ("provider_price_changed", "cloud_comment_changed", "cloud_review_changed"):
        assert not any(item.rebuild for item in matrix.plan(change, _artifacts()))


def test_provider_identity_only_invalidates_provider_dependent_artifacts() -> None:
    matrix = P2InvalidationMatrix()
    decisions = {
        item.artifact: item.rebuild
        for item in matrix.plan("provider_model_changed", _artifacts())
    }
    assert decisions == {
        "source": False,
        "llm": True,
        "tts": True,
        "render": True,
        "video": False,
        "final": False,
    }


def test_platform_runtime_and_revision_scopes_are_precise() -> None:
    matrix = P2InvalidationMatrix()
    platform = {
        item.artifact: item.rebuild
        for item in matrix.plan("platform_capability_changed", _artifacts())
    }
    assert platform == {
        "source": False,
        "llm": False,
        "tts": True,
        "render": True,
        "video": True,
        "final": True,
    }
    revision = {
        item.artifact: item.rebuild
        for item in matrix.plan("cloud_revision_changed", _artifacts())
    }
    assert all(revision.values())
