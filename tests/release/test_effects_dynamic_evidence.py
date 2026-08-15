from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.effects_dynamic_evidence import EffectsDynamicEvidenceError, build_raw_evidence


def _write_fixture(root: Path, *, complete: bool = True) -> tuple[Path, Path, Path, Path]:
    candidate = root / "candidate.json"
    candidate.write_text(
        json.dumps(
            {
                "candidate_id": "rc-test-20260815T000000Z",
                "source": {"git_commit": "a" * 40},
                "status": "candidate_frozen",
            }
        ),
        encoding="utf-8",
    )
    policy = root / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "policy_id": "effects-v2-acceptance",
                "effects_v2": {"persistence": True, "preview": True, "render": True},
            }
        ),
        encoding="utf-8",
    )
    sample = root / "samples.json"
    samples = [{"page_id": f"page-{index:03d}"} for index in range(1, 31)]
    sample.write_text(json.dumps({"samples": samples}), encoding="utf-8")
    artifacts = root / "artifacts"
    artifacts.mkdir()
    for item in samples:
        page_root = artifacts / item["page_id"]
        page_root.mkdir()
        (page_root / "preview.mp4").write_bytes(b"preview")
        if complete:
            (page_root / "final.mp4").write_bytes(b"final")
        metadata = {
            "effect_plan_sha256": "1" * 64,
            "render_graph_sha256": "2" * 64,
            "template_version": "effects-v2-test",
            "runtime_sha256": "3" * 64,
            "l3_enabled": False,
            "l3_allowed": True,
            "preview": {"frame_count": 30, "duration_ms": 1000},
            "final": {"frame_count": 30, "duration_ms": 1000},
        }
        (page_root / "page.json").write_text(json.dumps(metadata), encoding="utf-8")
    return candidate, policy, sample, artifacts


def test_builds_explicit_30_page_raw_evidence(tmp_path: Path) -> None:
    candidate, policy, sample, artifacts = _write_fixture(tmp_path)
    raw = build_raw_evidence(
        candidate_manifest=candidate,
        feature_policy=policy,
        sample_manifest=sample,
        artifact_root=artifacts,
    )
    assert raw["candidate_id"] == "rc-test-20260815T000000Z"
    assert len(raw["pages"]) == 30
    first = raw["pages"][0]
    assert first["preview"]["relative_path"] == "page-001/preview.mp4"
    assert first["preview"]["sha256"] == hashlib.sha256(b"preview").hexdigest()


def test_missing_installed_final_artifact_is_blocked(tmp_path: Path) -> None:
    candidate, policy, sample, artifacts = _write_fixture(tmp_path, complete=False)
    with pytest.raises(EffectsDynamicEvidenceError, match="page-001_final_missing"):
        build_raw_evidence(
            candidate_manifest=candidate,
            feature_policy=policy,
            sample_manifest=sample,
            artifact_root=artifacts,
        )
