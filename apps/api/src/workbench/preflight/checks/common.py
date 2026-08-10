from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid5

from workbench.domain.issues import IssueLevel, IssueLocation, PreflightIssue


def digest(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def issue(
    *,
    project_id: UUID,
    check: str,
    code: str,
    level: IssueLevel,
    message: str,
    action: str,
    fingerprint: str,
    location: IssueLocation | None = None,
    blocking: bool | None = None,
) -> PreflightIssue:
    clean_location = location or IssueLocation(node=check)
    identity = f"{project_id}:{check}:{code}:{clean_location.model_dump_json()}:{fingerprint}"
    return PreflightIssue(
        issue_id=uuid5(project_id, identity),
        check=check,
        code=code,
        level=level,
        message=message,
        action=action,
        location=clean_location,
        fingerprint=fingerprint,
        blocking=level is IssueLevel.BLOCKING if blocking is None else blocking,
    )


def relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
