"""Build candidate-bound raw Effects V2 evidence from installed-run artifacts.

The installed acceptance runner owns the actual preview/final rendering.  This
module only assembles the explicit artifacts it produced into the raw contract
consumed by :mod:`scripts.effects_dynamic_acceptance`; it never discovers a
latest directory or manufactures media evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scripts.effects_dynamic_acceptance import EffectsDynamicAcceptanceError, write_report


class EffectsDynamicEvidenceError(ValueError):
    """Raised when an installed-run artifact contract is incomplete."""


def _load(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise EffectsDynamicEvidenceError(f"{label}_invalid") from error
    if not isinstance(payload, dict):
        raise EffectsDynamicEvidenceError(f"{label}_object_required")
    return payload


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _relative(root: Path, path: Path, label: str) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise EffectsDynamicEvidenceError(f"{label}_outside_root") from error


def _artifact(root: Path, path: Path, metadata: Mapping[str, Any], label: str) -> dict[str, Any]:
    if not path.is_file():
        raise EffectsDynamicEvidenceError(f"{label}_missing")
    duration = metadata.get("duration_ms")
    frame_count = metadata.get("frame_count")
    if not isinstance(duration, (int, float)) or duration <= 0:
        raise EffectsDynamicEvidenceError(f"{label}_duration_invalid")
    if not isinstance(frame_count, int) or frame_count < 1:
        raise EffectsDynamicEvidenceError(f"{label}_frame_count_invalid")
    return {
        "relative_path": _relative(root, path, label),
        "size": path.stat().st_size,
        "sha256": _sha256(path),
        "frame_count": frame_count,
        "duration_ms": duration,
    }


def build_raw_evidence(
    *,
    candidate_manifest: Path,
    feature_policy: Path,
    sample_manifest: Path,
    artifact_root: Path,
) -> dict[str, Any]:
    candidate = _load(candidate_manifest, "candidate_manifest")
    candidate_id = candidate.get("candidate_id")
    source = candidate.get("source")
    commit = source.get("git_commit") if isinstance(source, Mapping) else None
    if not isinstance(candidate_id, str) or not candidate_id.startswith("rc-"):
        raise EffectsDynamicEvidenceError("candidate_id_invalid")
    if not isinstance(commit, str) or len(commit) != 40:
        raise EffectsDynamicEvidenceError("source_commit_invalid")
    policy = _load(feature_policy, "feature_policy")
    policy_id = policy.get("policy_id")
    if not isinstance(policy_id, str) or not policy_id:
        raise EffectsDynamicEvidenceError("feature_policy_id_missing")
    samples = _load(sample_manifest, "sample_manifest").get("samples")
    if not isinstance(samples, list) or len(samples) != 30:
        raise EffectsDynamicEvidenceError("sample_manifest_must_contain_30_samples")
    root = artifact_root.resolve()
    if not root.is_dir():
        raise EffectsDynamicEvidenceError("artifact_root_missing")
    pages: list[dict[str, Any]] = []
    for sample in samples:
        if not isinstance(sample, Mapping):
            raise EffectsDynamicEvidenceError("sample_record_invalid")
        page_id = sample.get("page_id")
        if not isinstance(page_id, str) or not page_id:
            raise EffectsDynamicEvidenceError("sample_page_id_missing")
        page_root = root / page_id
        metadata_path = page_root / "page.json"
        metadata = _load(metadata_path, f"{page_id}_metadata")
        preview = _artifact(
            root, page_root / "preview.mp4", metadata.get("preview", {}), f"{page_id}_preview"
        )
        final = _artifact(
            root, page_root / "final.mp4", metadata.get("final", {}), f"{page_id}_final"
        )
        fields = {
            key: metadata.get(key)
            for key in (
                "effect_plan_sha256",
                "render_graph_sha256",
                "template_version",
                "runtime_sha256",
                "l3_enabled",
                "l3_allowed",
            )
        }
        required_fields = (
            "effect_plan_sha256",
            "render_graph_sha256",
            "template_version",
            "runtime_sha256",
        )
        if not all(isinstance(fields[key], str) and fields[key] for key in required_fields):
            raise EffectsDynamicEvidenceError(f"{page_id}_identity_fields_missing")
        pages.append({"page_id": page_id, **fields, "preview": preview, "final": final})

    fallback_path = root / "fallback.json"
    fallback: dict[str, Any] | None = None
    if fallback_path.is_file():
        fallback = _load(fallback_path, "fallback")
        fallback.setdefault("candidate_id", candidate_id)
    return {
        "schema_version": "1.0",
        "candidate_id": candidate_id,
        "source_commit": commit,
        "feature_policy": {
            "policy_id": policy_id,
            "sha256": _sha256(feature_policy),
        },
        "pages": pages,
        "fallback": fallback,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--feature-policy", type=Path, required=True)
    parser.add_argument("--sample-manifest", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        raw = build_raw_evidence(
            candidate_manifest=args.candidate_manifest,
            feature_policy=args.feature_policy,
            sample_manifest=args.sample_manifest,
            artifact_root=args.artifact_root,
        )
        write_report(args.output, raw)
    except (
        EffectsDynamicEvidenceError,
        EffectsDynamicAcceptanceError,
        OSError,
        ValueError,
    ) as error:
        print(f"EFFECTS_DYNAMIC_EVIDENCE=BLOCK reason={error}")
        return 1
    print(f"EFFECTS_DYNAMIC_EVIDENCE=PASS candidate_id={raw['candidate_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
