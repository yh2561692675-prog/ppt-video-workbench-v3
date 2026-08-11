from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.verify_platform_evidence import EvidenceValidationError, validate_platform_evidence


def _artifact(evidence_type: str, platform: str = "linux") -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": 1,
        "evidence_type": evidence_type,
        "platform": platform,
        "runner_os": f"{platform}-runner-2026",
        "runner_arch": "x86_64",
        "real_runner": True,
        "status": "passed",
        "evidence_id": f"{platform}:{evidence_type}:20260811",
        "captured_at": "2026-08-11T10:00:00Z",
        "artifact_sha256": "sha256:" + "a" * 64,
    }
    if evidence_type == "runtime":
        payload.pop("artifact_sha256")
        payload["runtime"] = {
            "fingerprint": "sha256:" + "b" * 64,
            "media_exports": [
                {"name": "eight-page", "sha256": "sha256:" + "c" * 64, "duration_ms": 8000},
                {"name": "portrait", "sha256": "sha256:" + "d" * 64, "duration_ms": 4000},
            ],
        }
    elif evidence_type == "signature":
        payload.pop("artifact_sha256")
        payload["signature"] = {
            "algorithm": "ed25519",
            "verified": True,
            "certificate_subject": "release.example",
            "artifact_sha256": "sha256:" + "e" * 64,
        }
    return payload


def _write_evidence(root: Path, platform: str = "linux") -> None:
    directory = root / "artifacts" / "platform" / platform
    directory.mkdir(parents=True)
    for evidence_type in ("install", "upgrade", "rollback", "uninstall", "runtime", "signature"):
        (directory / f"{evidence_type}.json").write_text(
            json.dumps(_artifact(evidence_type, platform)), encoding="utf-8"
        )


def test_platform_evidence_validator_accepts_complete_contract_fixture(tmp_path: Path) -> None:
    _write_evidence(tmp_path)
    result = validate_platform_evidence(tmp_path, "linux")
    assert result["platform"] == "linux"
    assert len(result["artifacts"]) == 6


@pytest.mark.parametrize(
    ("evidence_type", "field", "value"),
    [
        ("install", "real_runner", False),
        ("install", "platform", "windows"),
        ("install", "runner_os", "windows-2022"),
        ("signature", "signature", {"algorithm": "mock", "verified": True}),
    ],
)
def test_platform_evidence_validator_rejects_untrusted_metadata(
    tmp_path: Path, evidence_type: str, field: str, value: object
) -> None:
    _write_evidence(tmp_path)
    path = tmp_path / "artifacts" / "platform" / "linux" / f"{evidence_type}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload[field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(EvidenceValidationError):
        validate_platform_evidence(tmp_path, "linux")
