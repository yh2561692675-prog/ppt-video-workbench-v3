from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.effects_dynamic_acceptance import build_report

COMMIT = "a" * 40
CANDIDATE = "rc-test-effects-20260814"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def _fixture(tmp_path: Path, *, pages: int = 1) -> tuple[Path, Path, Path, Path]:
    candidate = _write_json(
        tmp_path / "candidate.json",
        {
            "candidate_id": CANDIDATE,
            "status": "candidate_frozen",
            "source": {"git_commit": COMMIT, "dirty": False},
        },
    )
    policy = _write_json(
        tmp_path / "feature-policy.json",
        {
            "schema_version": "1.0",
            "policy_id": "effects-v2-acceptance",
            "candidate_id": CANDIDATE,
            "legacy_project_default": "v1",
            "new_project_default": "v2",
            "effects_v2": {"persistence": True, "preview": True, "render": True},
            "allow_fallback": True,
            "status": "acceptance",
        },
    )
    output_root = tmp_path / "output"
    output_root.mkdir()
    page_records: list[dict[str, object]] = []
    for index in range(pages):
        page_id = f"page-{index + 1:03d}"
        preview_path = output_root / "preview" / f"{page_id}.mp4"
        final_path = output_root / "final" / f"{page_id}.mp4"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_bytes(f"preview-{page_id}".encode())
        final_path.write_bytes(f"final-{page_id}".encode())
        effect_hash = hashlib.sha256(f"effect-{page_id}".encode()).hexdigest()
        graph_hash = hashlib.sha256(f"graph-{page_id}".encode()).hexdigest()
        runtime_hash = hashlib.sha256(b"runtime").hexdigest()
        page_records.append(
            {
                "page_id": page_id,
                "effect_plan_sha256": effect_hash,
                "render_graph_sha256": graph_hash,
                "template_version": "progressive-reveal@1.0.0",
                "runtime_sha256": runtime_hash,
                "preview": {
                    "relative_path": f"preview/{page_id}.mp4",
                    "size": preview_path.stat().st_size,
                    "sha256": _sha256(preview_path),
                    "frame_count": 30,
                    "duration_ms": 1000,
                },
                "final": {
                    "relative_path": f"final/{page_id}.mp4",
                    "size": final_path.stat().st_size,
                    "sha256": _sha256(final_path),
                    "frame_count": 30,
                    "duration_ms": 1000,
                },
            }
        )
    evidence = _write_json(
        tmp_path / "dynamic-evidence.json",
        {
            "schema_version": "1.0",
            "candidate_id": CANDIDATE,
            "source_commit": COMMIT,
            "feature_policy": {
                "policy_id": "effects-v2-acceptance",
                "sha256": _sha256(policy),
            },
            "pages": page_records,
            "fallback": {
                "status": "passed",
                "candidate_id": CANDIDATE,
                "page_count": pages,
                "policy_id": "effects-v1-safe-default",
            },
        },
    )
    return candidate, policy, evidence, output_root


def test_dynamic_evidence_passes_with_matching_candidate_and_artifacts(tmp_path: Path) -> None:
    candidate, policy, evidence, output_root = _fixture(tmp_path)

    report = build_report(
        candidate_manifest=candidate,
        feature_policy=policy,
        evidence=evidence,
        output_root=output_root,
        expected_pages=1,
        require_v2=True,
        require_fallback=True,
    )

    assert report["status"] == "passed"
    assert report["decision"] == "pass"
    assert report["summary"] == {
        "total_pages": 1,
        "preview_passed": 1,
        "final_passed": 1,
        "drift_count": 0,
        "missing_count": 0,
        "fallback_status": "passed",
    }


def test_tampered_final_artifact_fails_closed(tmp_path: Path) -> None:
    candidate, policy, evidence, output_root = _fixture(tmp_path)
    final_path = output_root / "final" / "page-001.mp4"
    final_path.write_bytes(b"X" * final_path.stat().st_size)

    report = build_report(
        candidate_manifest=candidate,
        feature_policy=policy,
        evidence=evidence,
        output_root=output_root,
        expected_pages=1,
    )

    assert report["status"] == "failed"
    assert "page-001_final_hash_mismatch" in report["blocking_failures"]


def test_wrong_candidate_is_stale_not_pass(tmp_path: Path) -> None:
    candidate, policy, evidence, output_root = _fixture(tmp_path)
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["candidate_id"] = "rc-other-20260814"
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    report = build_report(
        candidate_manifest=candidate,
        feature_policy=policy,
        evidence=evidence,
        output_root=output_root,
        expected_pages=1,
    )

    assert report["status"] == "stale"
    assert "candidate_mismatch:evidence" in report["blocking_failures"]


def test_missing_artifact_and_unsafe_reference_are_blocked(tmp_path: Path) -> None:
    candidate, policy, evidence, output_root = _fixture(tmp_path)
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["pages"][0]["preview"]["relative_path"] = "../outside.mp4"
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    report = build_report(
        candidate_manifest=candidate,
        feature_policy=policy,
        evidence=evidence,
        output_root=output_root,
        expected_pages=1,
    )

    assert report["status"] == "blocked"
    assert "page-001_preview_path_outside_root" in report["blocking_failures"]


def test_preview_final_frame_drift_is_failed(tmp_path: Path) -> None:
    candidate, policy, evidence, output_root = _fixture(tmp_path)
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["pages"][0]["final"]["frame_count"] = 29
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    report = build_report(
        candidate_manifest=candidate,
        feature_policy=policy,
        evidence=evidence,
        output_root=output_root,
        expected_pages=1,
    )

    assert report["status"] == "failed"
    assert "preview_final_frame_drift:page-001" in report["blocking_failures"]
