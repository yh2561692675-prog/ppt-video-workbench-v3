"""Small, dependency-light validators for the debug-program JSON contracts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any


class ValidationError(ValueError):
    """Raised when a debug-program contract is invalid."""


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_CANDIDATE = re.compile(r"^v1-rc-[a-z0-9]+-\d{8}T\d{6}Z$")
_RUN = re.compile(r"^[a-z0-9][a-z0-9-]{3,127}$")
_SCENARIO = re.compile(r"^DBG-[a-z0-9]+-\d{3}$")
_DEFECT = re.compile(r"^DEF-[a-z0-9-]+-\d{3}$")


def _required(data: dict[str, Any], names: tuple[str, ...]) -> None:
    missing = [name for name in names if name not in data]
    if missing:
        raise ValidationError(f"missing required fields: {', '.join(missing)}")


def _object(data: Any, name: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValidationError(f"{name} must be an object")
    return data


def _string(data: dict[str, Any], name: str) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{name} must be a non-empty string")
    return value


def _rfc3339(value: Any, name: str) -> None:
    if not isinstance(value, str):
        raise ValidationError(f"{name} must be an RFC3339 string")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{name} must be an RFC3339 string") from exc


def _relative_path(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{name} must be a relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValidationError(f"{name} must stay inside the candidate root")
    return value


def _hash_ref(value: Any, name: str) -> dict[str, Any]:
    item = _object(value, name)
    _required(item, ("path", "size", "sha256"))
    _relative_path(item["path"], f"{name}.path")
    if not isinstance(item["size"], int) or item["size"] < 0:
        raise ValidationError(f"{name}.size must be a non-negative integer")
    if not isinstance(item["sha256"], str) or not _SHA256.fullmatch(item["sha256"]):
        raise ValidationError(f"{name}.sha256 must be a lowercase SHA-256")
    return item


def _no_unknown(data: dict[str, Any], allowed: set[str], name: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValidationError(f"{name} has unknown fields: {', '.join(unknown)}")


def validate_candidate_manifest(data: Any, base_dir: Path | None = None) -> dict[str, Any]:
    item = _object(data, "candidate")
    _required(item, ("schema_version", "candidate_id", "generated_at", "source", "files"))
    _no_unknown(
        item,
        {
            "schema_version",
            "candidate_id",
            "generated_at",
            "source",
            "files",
            "runtime",
            "features",
            "installer",
        },
        "candidate",
    )
    if item["schema_version"] != "1.0":
        raise ValidationError("candidate.schema_version must be 1.0")
    candidate_id = _string(item, "candidate_id")
    if not _CANDIDATE.fullmatch(candidate_id):
        raise ValidationError("candidate_id must match v1-rc-<short-git>-<UTC timestamp>")
    _rfc3339(item["generated_at"], "generated_at")
    source = _object(item["source"], "source")
    _required(source, ("commit", "branch", "dirty"))
    _no_unknown(source, {"commit", "branch", "dirty"}, "source")
    if not isinstance(source["commit"], str) or not _COMMIT.fullmatch(source["commit"]):
        raise ValidationError("source.commit must be a 40-character lowercase commit")
    _string(source, "branch")
    if not isinstance(source["dirty"], bool):
        raise ValidationError("source.dirty must be boolean")
    if source["dirty"]:
        raise ValidationError("dirty source is not a release candidate")
    files = item["files"]
    if not isinstance(files, list) or not files:
        raise ValidationError("files must be a non-empty array")
    seen: set[str] = set()
    for index, value in enumerate(files):
        ref = _hash_ref(value, f"files[{index}]")
        if ref["path"] in seen:
            raise ValidationError(f"duplicate file reference: {ref['path']}")
        seen.add(ref["path"])
        if base_dir is not None:
            path = (base_dir / ref["path"]).resolve()
            if base_dir.resolve() not in path.parents and path != base_dir.resolve():
                raise ValidationError(f"file escapes candidate root: {ref['path']}")
            if not path.is_file():
                raise ValidationError(f"candidate file is missing: {ref['path']}")
            if path.stat().st_size != ref["size"]:
                raise ValidationError(f"size mismatch for {ref['path']}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != ref["sha256"]:
                raise ValidationError(f"sha256 mismatch for {ref['path']}")
    if "installer" in item:
        _hash_ref(item["installer"], "installer")
    if "runtime" in item:
        _object(item["runtime"], "runtime")
    if "features" in item and not isinstance(item["features"], dict):
        raise ValidationError("features must be an object")
    return item


def validate_scenario(data: Any) -> dict[str, Any]:
    item = _object(data, "scenario")
    _required(
        item,
        (
            "schema_version",
            "scenario_id",
            "title",
            "matrix",
            "risk",
            "platform",
            "owner",
            "steps",
            "destructive",
            "paid",
            "manual",
        ),
    )
    _no_unknown(
        item,
        {
            "schema_version",
            "scenario_id",
            "title",
            "matrix",
            "risk",
            "platform",
            "owner",
            "feature_flags",
            "fixture",
            "steps",
            "destructive",
            "paid",
            "manual",
            "resources",
            "cleanup",
        },
        "scenario",
    )
    if item["schema_version"] != "1.0":
        raise ValidationError("scenario.schema_version must be 1.0")
    if not isinstance(item["scenario_id"], str) or not _SCENARIO.fullmatch(item["scenario_id"]):
        raise ValidationError("scenario_id must match DBG-<domain>-<number>")
    for field in ("title", "matrix", "risk", "platform", "owner"):
        _string(item, field)
    if item["risk"] not in {"P0", "P1", "P2", "P3"}:
        raise ValidationError("risk must be P0, P1, P2 or P3")
    if (
        not isinstance(item["steps"], list)
        or not item["steps"]
        or not all(isinstance(v, str) and v for v in item["steps"])
    ):
        raise ValidationError("steps must be a non-empty string array")
    for field in ("destructive", "paid", "manual"):
        if not isinstance(item[field], bool):
            raise ValidationError(f"{field} must be boolean")
    if (item["destructive"] or item["paid"]) and (
        not item.get("feature_flags") or not item.get("authorization_scope")
    ):
        raise ValidationError(
            "destructive or paid scenarios require feature_flags and authorization_scope"
        )
    return item


def validate_run(data: Any) -> dict[str, Any]:
    item = _object(data, "run")
    _required(
        item,
        (
            "schema_version",
            "run_id",
            "candidate_id",
            "matrix",
            "started_at",
            "attempt",
            "status",
            "artifacts",
            "orphan_processes",
        ),
    )
    _no_unknown(
        item,
        {
            "schema_version",
            "run_id",
            "candidate_id",
            "matrix",
            "platform",
            "started_at",
            "finished_at",
            "attempt",
            "status",
            "artifacts",
            "orphan_processes",
            "environment",
        },
        "run",
    )
    if item["schema_version"] != "1.0":
        raise ValidationError("run.schema_version must be 1.0")
    if not isinstance(item["run_id"], str) or not _RUN.fullmatch(item["run_id"]):
        raise ValidationError("run_id is invalid")
    if not isinstance(item["candidate_id"], str) or not _CANDIDATE.fullmatch(item["candidate_id"]):
        raise ValidationError("run.candidate_id is invalid")
    _string(item, "matrix")
    _rfc3339(item["started_at"], "started_at")
    if "finished_at" in item and item["finished_at"] is not None:
        _rfc3339(item["finished_at"], "finished_at")
    if not isinstance(item["attempt"], int) or item["attempt"] < 1:
        raise ValidationError("attempt must be positive")
    if item["status"] not in {"planned", "running", "passed", "failed", "blocked", "interrupted"}:
        raise ValidationError("run.status is invalid")
    if not isinstance(item["artifacts"], list) or not all(
        isinstance(v, dict) for v in item["artifacts"]
    ):
        raise ValidationError("artifacts must be an array")
    if not isinstance(item["orphan_processes"], list) or not all(
        isinstance(v, int) and v > 0 for v in item["orphan_processes"]
    ):
        raise ValidationError("orphan_processes must be positive process IDs")
    return item


def validate_automation_verdict(
    data: Any, base_dir: Path | None = None
) -> dict[str, Any]:
    """Validate the append-only verdict emitted by the automation runner."""

    item = _object(data, "automation_verdict")
    _required(
        item,
        (
            "schema_version",
            "candidate_id",
            "run_id",
            "matrix",
            "status",
            "started_at",
            "finished_at",
            "commands",
            "first_failure",
        ),
    )
    _no_unknown(
        item,
        {
            "schema_version",
            "candidate_id",
            "run_id",
            "matrix",
            "status",
            "started_at",
            "finished_at",
            "commands",
            "first_failure",
            "notes",
        },
        "automation_verdict",
    )
    if item["schema_version"] != "1.0":
        raise ValidationError("automation_verdict.schema_version must be 1.0")
    if not isinstance(item["candidate_id"], str) or not _CANDIDATE.fullmatch(
        item["candidate_id"]
    ):
        raise ValidationError("automation_verdict.candidate_id is invalid")
    if not isinstance(item["run_id"], str) or not _RUN.fullmatch(item["run_id"]):
        raise ValidationError("automation_verdict.run_id is invalid")
    _string(item, "matrix")
    if item["status"] not in {"passed", "failed", "blocked", "interrupted"}:
        raise ValidationError("automation_verdict.status is invalid")
    _rfc3339(item["started_at"], "started_at")
    _rfc3339(item["finished_at"], "finished_at")
    commands = item["commands"]
    if not isinstance(commands, list):
        raise ValidationError("automation_verdict.commands must be an array")
    for index, command in enumerate(commands):
        entry = _object(command, f"commands[{index}]")
        _required(entry, ("name", "exit_code", "status", "result"))
        _no_unknown(entry, {"name", "exit_code", "status", "result"}, f"commands[{index}]")
        _string(entry, "name")
        if not isinstance(entry["exit_code"], int):
            raise ValidationError(f"commands[{index}].exit_code must be an integer")
        if entry["status"] not in {"passed", "failed"}:
            raise ValidationError(f"commands[{index}].status is invalid")
        relative = _relative_path(entry["result"], f"commands[{index}].result")
        if base_dir is not None and not (base_dir / relative).is_file():
            raise ValidationError(f"missing automation result: {relative}")
    failure = item["first_failure"]
    if failure is not None:
        entry = _object(failure, "first_failure")
        _required(entry, ("name", "exit_code", "result"))
        _no_unknown(entry, {"name", "exit_code", "result"}, "first_failure")
        _string(entry, "name")
        if not isinstance(entry["exit_code"], int):
            raise ValidationError("first_failure.exit_code must be an integer")
        relative = _relative_path(entry["result"], "first_failure.result")
        if base_dir is not None and not (base_dir / relative).is_file():
            raise ValidationError(f"missing first failure result: {relative}")
    if item["status"] == "failed" and failure is None:
        raise ValidationError("failed automation verdict requires first_failure")
    if "notes" in item and not isinstance(item["notes"], list):
        raise ValidationError("automation_verdict.notes must be an array")
    return item


def validate_defect(data: Any) -> dict[str, Any]:
    item = _object(data, "defect")
    _required(
        item,
        (
            "schema_version",
            "defect_id",
            "severity",
            "owner",
            "title",
            "reproduction",
            "status",
            "candidate_id",
        ),
    )
    _no_unknown(
        item,
        {
            "schema_version",
            "defect_id",
            "severity",
            "owner",
            "title",
            "reproduction",
            "fix_commit",
            "status",
            "candidate_id",
            "closed_at",
            "waiver",
        },
        "defect",
    )
    if item["schema_version"] != "1.0":
        raise ValidationError("defect.schema_version must be 1.0")
    if not isinstance(item["defect_id"], str) or not _DEFECT.fullmatch(item["defect_id"]):
        raise ValidationError("defect_id is invalid")
    if item["severity"] not in {"P0", "P1", "P2", "P3"}:
        raise ValidationError("severity is invalid")
    for field in ("owner", "title", "reproduction", "candidate_id"):
        _string(item, field)
    if not _CANDIDATE.fullmatch(item["candidate_id"]):
        raise ValidationError("defect.candidate_id is invalid")
    if item["status"] not in {"open", "fixed", "verified", "waived", "blocked"}:
        raise ValidationError("defect.status is invalid")
    if item["status"] in {"fixed", "verified"}:
        commit = item.get("fix_commit")
        if not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
            raise ValidationError("fixed defects require a 40-character fix_commit")
    return item


def validate_signoff(data: Any) -> dict[str, Any]:
    item = _object(data, "signoff")
    _required(
        item,
        (
            "schema_version",
            "candidate_id",
            "role",
            "reviewer",
            "decision",
            "signed_at",
            "evidence_hashes",
        ),
    )
    _no_unknown(
        item,
        {
            "schema_version",
            "candidate_id",
            "role",
            "reviewer",
            "decision",
            "signed_at",
            "evidence_hashes",
            "notes",
        },
        "signoff",
    )
    if item["schema_version"] != "1.0":
        raise ValidationError("signoff.schema_version must be 1.0")
    if not isinstance(item["candidate_id"], str) or not _CANDIDATE.fullmatch(item["candidate_id"]):
        raise ValidationError("signoff.candidate_id is invalid")
    for field in ("role", "reviewer"):
        _string(item, field)
    if item["decision"] not in {"approved", "rejected", "blocked"}:
        raise ValidationError("signoff.decision is invalid")
    _rfc3339(item["signed_at"], "signed_at")
    hashes = item["evidence_hashes"]
    if (
        not isinstance(hashes, list)
        or not hashes
        or not all(isinstance(v, str) and _SHA256.fullmatch(v) for v in hashes)
    ):
        raise ValidationError("evidence_hashes must contain SHA-256 values")
    return item


def load_and_validate(
    path: Path, validator: Callable[..., dict[str, Any]], base_dir: Path | None = None
) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read JSON contract {path}: {exc}") from exc
    if base_dir is None:
        return validator(value)
    return validator(value, base_dir)
