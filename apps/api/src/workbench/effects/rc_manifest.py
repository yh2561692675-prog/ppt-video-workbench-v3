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
    resolved_root = root.resolve()
    installer = (resolved_root / candidate.installer_relative_path).resolve()
    reasons: list[str] = []
    if not installer.is_relative_to(resolved_root):
        reasons.append("installer_path_outside_repository")
        return {"valid": False, "rc_id": candidate.rc_id, "reason_codes": reasons}
    if installer.exists() and sha256_file(installer) != candidate.installer_sha256:
        reasons.append("installer_sha256_mismatch")
    if not installer.exists():
        reasons.append("installer_not_found")
    return {"valid": not reasons, "rc_id": candidate.rc_id, "reason_codes": reasons}
