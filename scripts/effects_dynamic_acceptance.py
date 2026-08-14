"""Fail-closed verifier for candidate-bound Effects V2 dynamic evidence.

The verifier intentionally consumes explicit paths.  It never discovers a
"latest" candidate or trusts mtime-only evidence.  Windows runners can first
write a raw evidence JSON and then call this module to produce the immutable
stage result used by the final closure aggregator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT40 = re.compile(r"^[0-9a-f]{40}$")
_CANDIDATE = re.compile(r"^rc-[A-Za-z0-9][A-Za-z0-9._-]*$")


class EffectsDynamicAcceptanceError(ValueError):
    """Raised for malformed verifier inputs."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise EffectsDynamicAcceptanceError(f"{label}_invalid") from error
    if not isinstance(value, dict):
        raise EffectsDynamicAcceptanceError(f"{label}_object_required")
    return value


def _safe_relative(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise EffectsDynamicAcceptanceError(f"{label}_path_invalid")
    relative = Path(value)
    if ".." in relative.parts:
        raise EffectsDynamicAcceptanceError(f"{label}_path_outside_root")
    resolved_root = root.resolve()
    resolved = (resolved_root / relative).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise EffectsDynamicAcceptanceError(f"{label}_path_outside_root")
    return resolved


def _candidate_identity(path: Path) -> tuple[str, str]:
    manifest = _load_object(path, "candidate_manifest")
    candidate_id = manifest.get("candidate_id")
    if not isinstance(candidate_id, str) or not _CANDIDATE.fullmatch(candidate_id):
        raise EffectsDynamicAcceptanceError("candidate_id_invalid")
    status = manifest.get("status")
    if status is not None and status not in {"candidate_frozen", "release_artifacts_ready"}:
        raise EffectsDynamicAcceptanceError(f"candidate_not_frozen:{status}")
    source = manifest.get("source")
    if not isinstance(source, Mapping):
        raise EffectsDynamicAcceptanceError("candidate_source_missing")
    commit = source.get("git_commit")
    if not isinstance(commit, str) or not _COMMIT40.fullmatch(commit):
        raise EffectsDynamicAcceptanceError("candidate_source_commit_invalid")
    return candidate_id, commit


def _feature_policy(path: Path, candidate_id: str) -> tuple[str, str, bool, str | None]:
    policy = _load_object(path, "feature_policy")
    policy_id = policy.get("policy_id")
    if not isinstance(policy_id, str) or not policy_id:
        raise EffectsDynamicAcceptanceError("feature_policy_id_missing")
    policy_candidate = policy.get("candidate_id")
    if policy_candidate not in (None, candidate_id):
        raise EffectsDynamicAcceptanceError("feature_policy_candidate_mismatch")
    effects = policy.get("effects_v2")
    if not isinstance(effects, Mapping):
        raise EffectsDynamicAcceptanceError("feature_policy_effects_v2_missing")
    v2_enabled = all(effects.get(name) is True for name in ("persistence", "preview", "render"))
    new_project_default = policy.get("new_project_default")
    if new_project_default is not None and not isinstance(new_project_default, str):
        raise EffectsDynamicAcceptanceError("feature_policy_new_project_default_invalid")
    return policy_id, sha256_file(path), v2_enabled, new_project_default


def _artifact(
    record: object,
    *,
    root: Path,
    label: str,
    blockers: list[str],
) -> tuple[dict[str, Any], bool]:
    if not isinstance(record, Mapping):
        blockers.append(f"{label}_record_invalid")
        return {}, False
    try:
        path = _safe_relative(root, record.get("relative_path"), label)
    except EffectsDynamicAcceptanceError as error:
        blockers.append(str(error))
        return {}, False
    expected_size = record.get("size")
    expected_hash = record.get("sha256")
    frame_count = record.get("frame_count")
    duration_ms = record.get("duration_ms")
    valid = True
    if not isinstance(expected_size, int) or expected_size < 0:
        blockers.append(f"{label}_size_invalid")
        valid = False
    if not isinstance(expected_hash, str) or not _HEX64.fullmatch(expected_hash):
        blockers.append(f"{label}_sha256_invalid")
        valid = False
    if not isinstance(frame_count, int) or frame_count < 1:
        blockers.append(f"{label}_frame_count_invalid")
        valid = False
    if not isinstance(duration_ms, (int, float)) or duration_ms <= 0:
        blockers.append(f"{label}_duration_invalid")
        valid = False
    if not path.is_file():
        blockers.append(f"{label}_missing")
        return dict(record), False
    if valid and path.stat().st_size != expected_size:
        blockers.append(f"{label}_size_mismatch")
        valid = False
    if valid and sha256_file(path) != expected_hash:
        blockers.append(f"{label}_hash_mismatch")
        valid = False
    result = dict(record)
    result["relative_path"] = path.relative_to(root.resolve()).as_posix()
    return result, valid


def _status(blockers: list[str]) -> str:
    if not blockers:
        return "passed"
    if any(
        token in blocker
        for blocker in blockers
        for token in ("candidate_mismatch", "source_commit_mismatch", "policy_mismatch", "stale")
    ):
        return "stale"
    if any(
        token in blocker
        for blocker in blockers
        for token in ("missing", "invalid", "outside_root", "not_frozen", "required")
    ):
        return "blocked"
    return "failed"


def build_report(
    *,
    candidate_manifest: Path,
    feature_policy: Path,
    evidence: Path,
    output_root: Path,
    expected_pages: int = 30,
    duration_tolerance_ms: float = 100.0,
    require_v2: bool = False,
    require_fallback: bool = False,
) -> dict[str, Any]:
    """Validate explicit dynamic evidence and return a stage report."""

    if expected_pages < 1:
        raise EffectsDynamicAcceptanceError("expected_pages_invalid")
    candidate_id, source_commit = _candidate_identity(candidate_manifest)
    policy_id, policy_sha256, v2_enabled, new_project_default = _feature_policy(
        feature_policy, candidate_id
    )
    raw = _load_object(evidence, "dynamic_evidence")
    blockers: list[str] = []
    if raw.get("schema_version") != SCHEMA_VERSION:
        blockers.append("dynamic_evidence_schema_version_invalid")
    if raw.get("candidate_id") != candidate_id:
        blockers.append("candidate_mismatch:evidence")
    if raw.get("source_commit") != source_commit:
        blockers.append("source_commit_mismatch:evidence")
    raw_policy = raw.get("feature_policy")
    if not isinstance(raw_policy, Mapping):
        blockers.append("feature_policy_evidence_missing")
    else:
        if raw_policy.get("policy_id") != policy_id:
            blockers.append("policy_mismatch:id")
        if raw_policy.get("sha256") != policy_sha256:
            blockers.append("policy_mismatch:sha256")
    if require_v2:
        if not v2_enabled:
            blockers.append("feature_policy_v2_required")
        if new_project_default != "v2":
            blockers.append("feature_policy_v2_default_required")
    try:
        output_root_resolved = output_root.resolve()
    except OSError as error:
        raise EffectsDynamicAcceptanceError("output_root_invalid") from error
    pages = raw.get("pages")
    if not isinstance(pages, list):
        blockers.append("pages_missing")
        pages = []
    if len(pages) != expected_pages:
        blockers.append(f"page_count_mismatch:expected={expected_pages}:actual={len(pages)}")

    page_reports: list[dict[str, Any]] = []
    seen_page_ids: set[str] = set()
    preview_passed = 0
    final_passed = 0
    drift_count = 0
    missing_count = 0
    for index, page in enumerate(pages):
        page_label = f"page[{index}]"
        if not isinstance(page, Mapping):
            blockers.append(f"{page_label}_record_invalid")
            continue
        page_id = page.get("page_id")
        if not isinstance(page_id, str) or not page_id:
            blockers.append(f"{page_label}_id_missing")
            page_id = f"index-{index + 1}"
        elif page_id in seen_page_ids:
            blockers.append(f"duplicate_page_id:{page_id}")
        seen_page_ids.add(page_id)
        for field in ("effect_plan_sha256", "render_graph_sha256", "runtime_sha256"):
            value = page.get(field)
            if not isinstance(value, str) or not _HEX64.fullmatch(value):
                blockers.append(f"{page_id}_{field}_invalid")
        template_version = page.get("template_version")
        if not isinstance(template_version, str) or not template_version:
            blockers.append(f"{page_id}_template_version_invalid")
        if page.get("l3_enabled") is True and page.get("l3_allowed") is not True:
            blockers.append(f"l3_not_allowed:{page_id}")

        preview, preview_ok = _artifact(
            page.get("preview"),
            root=output_root_resolved,
            label=f"{page_id}_preview",
            blockers=blockers,
        )
        final, final_ok = _artifact(
            page.get("final"),
            root=output_root_resolved,
            label=f"{page_id}_final",
            blockers=blockers,
        )
        if preview_ok:
            preview_passed += 1
        else:
            if any(item.startswith(f"{page_id}_preview_missing") for item in blockers):
                missing_count += 1
        if final_ok:
            final_passed += 1
        else:
            if any(item.startswith(f"{page_id}_final_missing") for item in blockers):
                missing_count += 1
        if preview_ok and final_ok:
            if preview.get("frame_count") != final.get("frame_count"):
                blockers.append(f"preview_final_frame_drift:{page_id}")
                drift_count += 1
            preview_duration = float(preview.get("duration_ms", 0))
            final_duration = float(final.get("duration_ms", 0))
            if abs(preview_duration - final_duration) > duration_tolerance_ms:
                blockers.append(f"preview_final_duration_drift:{page_id}")
                drift_count += 1
        page_reports.append(
            {
                "page_id": page_id,
                "effect_plan_sha256": page.get("effect_plan_sha256"),
                "render_graph_sha256": page.get("render_graph_sha256"),
                "template_version": template_version,
                "runtime_sha256": page.get("runtime_sha256"),
                "preview": preview,
                "final": final,
            }
        )

    fallback = raw.get("fallback")
    fallback_status = "not_required"
    if fallback is not None:
        if not isinstance(fallback, Mapping):
            blockers.append("fallback_record_invalid")
            fallback_status = "blocked"
        else:
            fallback_status = str(fallback.get("status", "blocked"))
            if fallback.get("candidate_id") != candidate_id:
                blockers.append("fallback_candidate_mismatch")
            if fallback_status != "passed":
                blockers.append(f"fallback_not_passed:{fallback_status}")
    elif require_fallback:
        blockers.append("fallback_required")
        fallback_status = "blocked"

    status = _status(blockers)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "decision": "pass" if status == "passed" else "block",
        "candidate_id": candidate_id,
        "source_commit": source_commit,
        "feature_policy": {
            "policy_id": policy_id,
            "relative_path": feature_policy.name,
            "sha256": policy_sha256,
        },
        "pages": page_reports,
        "fallback": dict(fallback) if isinstance(fallback, Mapping) else None,
        "summary": {
            "total_pages": len(pages),
            "preview_passed": preview_passed,
            "final_passed": final_passed,
            "drift_count": drift_count,
            "missing_count": missing_count,
            "fallback_status": fallback_status,
        },
        "blocking_failures": sorted(set(blockers)),
    }


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.partial")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--feature-policy", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-pages", type=int, default=30)
    parser.add_argument("--duration-tolerance-ms", type=float, default=100.0)
    parser.add_argument("--require-v2", action="store_true")
    parser.add_argument("--require-fallback", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = build_report(
            candidate_manifest=args.candidate_manifest,
            feature_policy=args.feature_policy,
            evidence=args.evidence,
            output_root=args.output_root,
            expected_pages=args.expected_pages,
            duration_tolerance_ms=args.duration_tolerance_ms,
            require_v2=args.require_v2,
            require_fallback=args.require_fallback,
        )
        write_report(args.output, report)
    except (EffectsDynamicAcceptanceError, OSError, ValueError) as error:
        print(f"EFFECTS_DYNAMIC_ACCEPTANCE=BLOCK reason={error}")
        return 1
    if report["status"] == "passed":
        print(f"EFFECTS_DYNAMIC_ACCEPTANCE=PASS candidate_id={report['candidate_id']}")
        return 0
    print(
        "EFFECTS_DYNAMIC_ACCEPTANCE=BLOCK "
        f"status={report['status']} blockers={','.join(report['blocking_failures'])}"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
