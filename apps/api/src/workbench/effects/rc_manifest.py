"""RC manifest validation and deterministic JSON helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .release_models import ReleaseCandidate


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_rc_manifest(path: Path) -> ReleaseCandidate:
    data = json.loads(path.read_text(encoding="utf-8"))
    return ReleaseCandidate.from_dict(data)


def verify_rc_manifest(path: Path, root: Path) -> dict[str, Any]:
    candidate = load_rc_manifest(path)
    installer = root / "release" / "ppt-video-workbench-setup.exe"
    reasons: list[str] = []
    if installer.exists() and sha256_file(installer) != candidate.installer_sha256:
        reasons.append("installer_sha256_mismatch")
    if not installer.exists():
        reasons.append("installer_not_found")
    return {"valid": not reasons, "rc_id": candidate.rc_id, "reason_codes": reasons}
