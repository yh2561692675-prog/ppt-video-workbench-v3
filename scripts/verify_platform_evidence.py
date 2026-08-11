"""Validate real three-platform release evidence without creating evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PLATFORMS = {"windows", "macos", "linux"}
ARTIFACTS = ("install", "upgrade", "rollback", "uninstall", "runtime", "signature")
SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
FORBIDDEN_SIGNATURE_ALGORITHMS = {"none", "mock", "fake", "test"}
RUNNER_OS_MARKERS = {
    "windows": ("windows",),
    "macos": ("macos", "darwin"),
    "linux": ("linux", "ubuntu", "debian", "fedora"),
}


class EvidenceValidationError(ValueError):
    """Raised when a platform evidence artifact cannot satisfy the release gate."""


def _require_string(payload: dict[str, Any], key: str, *, max_length: int = 500) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise EvidenceValidationError(f"{key} must be a non-empty bounded string")
    return value


def _require_sha256(value: Any, key: str) -> None:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise EvidenceValidationError(f"{key} must use sha256:<64 lowercase hex>")


def _validate_timestamp(value: Any) -> None:
    if not isinstance(value, str):
        raise EvidenceValidationError("captured_at must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvidenceValidationError("captured_at must be an RFC3339 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceValidationError("captured_at must include a timezone")


def _validate_signature(payload: dict[str, Any]) -> None:
    signature = payload.get("signature")
    if not isinstance(signature, dict):
        raise EvidenceValidationError("signature evidence requires a signature object")
    algorithm = _require_string(signature, "algorithm", max_length=100).lower()
    if algorithm in FORBIDDEN_SIGNATURE_ALGORITHMS:
        raise EvidenceValidationError("signature algorithm must describe a real signer")
    if signature.get("verified") is not True:
        raise EvidenceValidationError("signature must be verified by the runner")
    _require_string(signature, "certificate_subject")
    _require_sha256(signature.get("artifact_sha256"), "signature.artifact_sha256")


def _validate_runtime(payload: dict[str, Any]) -> None:
    runtime = payload.get("runtime")
    if not isinstance(runtime, dict):
        raise EvidenceValidationError("runtime evidence requires a runtime object")
    _require_sha256(runtime.get("fingerprint"), "runtime.fingerprint")
    exports = runtime.get("media_exports")
    if not isinstance(exports, list) or len(exports) < 2:
        raise EvidenceValidationError("runtime evidence requires at least two media exports")
    for index, export in enumerate(exports):
        if not isinstance(export, dict):
            raise EvidenceValidationError(f"runtime.media_exports[{index}] must be an object")
        _require_string(export, "name", max_length=100)
        _require_sha256(export.get("sha256"), f"runtime.media_exports[{index}].sha256")
        duration_ms = export.get("duration_ms")
        if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or duration_ms < 1:
            raise EvidenceValidationError(
                f"runtime.media_exports[{index}].duration_ms must be a positive integer"
            )


def validate_artifact(payload: dict[str, Any], *, platform: str, evidence_type: str) -> None:
    if payload.get("schema_version") != 1:
        raise EvidenceValidationError("schema_version must be 1")
    if payload.get("evidence_type") != evidence_type:
        raise EvidenceValidationError(f"evidence_type must be {evidence_type}")
    if payload.get("platform") != platform:
        raise EvidenceValidationError(f"platform must be {platform}")
    runner_os = _require_string(payload, "runner_os", max_length=200).lower()
    if not any(marker in runner_os for marker in RUNNER_OS_MARKERS[platform]):
        raise EvidenceValidationError(f"runner_os does not identify a {platform} runner")
    _require_string(payload, "runner_arch", max_length=64)
    if payload.get("real_runner") is not True:
        raise EvidenceValidationError("real_runner must be true")
    if payload.get("status") != "passed":
        raise EvidenceValidationError("status must be passed")
    _require_string(payload, "evidence_id", max_length=128)
    _validate_timestamp(payload.get("captured_at"))
    if evidence_type != "runtime" and evidence_type != "signature":
        _require_sha256(payload.get("artifact_sha256"), "artifact_sha256")
    if evidence_type == "signature":
        _validate_signature(payload)
    if evidence_type == "runtime":
        _validate_runtime(payload)


def validate_platform_evidence(root: Path, platform: str) -> dict[str, Any]:
    if platform not in PLATFORMS:
        raise EvidenceValidationError(f"unsupported platform: {platform}")
    evidence_root = (root / "artifacts" / "platform" / platform).resolve()
    try:
        evidence_root.relative_to(root.resolve())
    except ValueError as error:
        raise EvidenceValidationError("evidence path escaped repository root") from error
    results: dict[str, Any] = {"platform": platform, "artifacts": []}
    for evidence_type in ARTIFACTS:
        path = evidence_root / f"{evidence_type}.json"
        if not path.is_file() or path.stat().st_size == 0:
            raise EvidenceValidationError(f"missing evidence artifact: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise EvidenceValidationError(f"invalid JSON artifact: {path}") from error
        if not isinstance(payload, dict):
            raise EvidenceValidationError(f"evidence artifact must be an object: {path}")
        validate_artifact(payload, platform=platform, evidence_type=evidence_type)
        results["artifacts"].append(
            {"type": evidence_type, "evidence_id": payload["evidence_id"]}
        )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--platform", choices=sorted(PLATFORMS), required=True)
    args = parser.parse_args(argv)
    try:
        result = validate_platform_evidence(args.root, args.platform)
    except EvidenceValidationError as error:
        print(f"platform evidence rejected: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
