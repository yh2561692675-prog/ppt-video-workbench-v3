"""Strict validator for externally executed Windows/Ubuntu CI evidence."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path, PureWindowsPath
from typing import Any
from urllib.parse import urlparse

from .models import (
    _CANDIDATE,
    _COMMIT,
    _SHA256,
    ValidationError,
    _hash_ref,
    _no_unknown,
    _object,
    _relative_path,
    _required,
    _rfc3339,
    _string,
    validate_candidate_manifest,
)

_SCHEMA_VERSION = "1.0"
_PLATFORMS = {"windows", "ubuntu"}
_HASH_GROUPS = ("artifacts", "logs", "reports", "traces")
_PATH_SEPARATOR = re.compile(r"[/\\]")
_RFC3339 = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inside(path: Path, root: Path, name: str) -> Path:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValidationError(f"{name} escapes evidence root")
    return resolved


def _strict_relative_path(value: Any, name: str) -> str:
    """Reject POSIX, Windows, UNC, traversal and drive-qualified paths."""

    relative = _relative_path(value, name)
    windows = PureWindowsPath(relative)
    if windows.is_absolute() or windows.drive or windows.root:
        raise ValidationError(f"{name} must be a relative path")
    parts = [part for part in _PATH_SEPARATOR.split(relative) if part]
    if any(part == ".." for part in parts):
        raise ValidationError(f"{name} must stay inside the evidence root")
    return relative


def _strict_timestamp(value: Any, name: str) -> datetime:
    if not isinstance(value, str) or not _RFC3339.fullmatch(value):
        raise ValidationError(f"{name} must be an RFC3339 timestamp with timezone")
    _rfc3339(value, name)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _validate_hash_files(
    values: Any, name: str, evidence_root: Path, seen_paths: set[str]
) -> None:
    if not isinstance(values, list) or not values:
        raise ValidationError(f"{name} must be a non-empty array")
    for index, raw_ref in enumerate(values):
        ref = _hash_ref(raw_ref, f"{name}[{index}]")
        _no_unknown(ref, {"path", "size", "sha256"}, f"{name}[{index}]")
        relative = _strict_relative_path(ref["path"], f"{name}[{index}].path")
        if isinstance(ref["size"], bool):
            raise ValidationError(f"{name}[{index}].size must be an integer")
        key = relative.replace("\\", "/").casefold()
        if key in seen_paths:
            raise ValidationError(f"duplicate evidence file reference: {relative}")
        seen_paths.add(key)
        path = _inside(evidence_root / relative, evidence_root, f"{name}[{index}].path")
        if not path.is_file():
            raise ValidationError(f"missing evidence file: {relative}")
        if path.stat().st_size != ref["size"]:
            raise ValidationError(f"size mismatch for evidence file: {relative}")
        if _sha256(path) != ref["sha256"]:
            raise ValidationError(f"sha256 mismatch for evidence file: {relative}")


def _validate_job(value: Any, index: int, evidence_root: Path) -> tuple[str, str, str]:
    job = _object(value, f"jobs[{index}]")
    fields = {
        "platform",
        "job_id",
        "conclusion",
        "e2e",
        "quality",
        "run_id",
        "url",
        "started_at",
        "finished_at",
        "artifacts",
        "logs",
        "reports",
        "traces",
    }
    _required(job, tuple(fields))
    _no_unknown(job, fields, f"jobs[{index}]")
    platform = job["platform"]
    if platform not in _PLATFORMS:
        raise ValidationError(f"jobs[{index}].platform is invalid")
    job_id = _string(job, "job_id")
    if job["conclusion"] != "success":
        raise ValidationError(f"jobs[{index}].conclusion must be success")
    e2e = _object(job["e2e"], f"jobs[{index}].e2e")
    _required(e2e, ("command", "exit_code", "conclusion"))
    _no_unknown(e2e, {"command", "exit_code", "conclusion"}, f"jobs[{index}].e2e")
    if (
        e2e["command"] != "pnpm e2e"
        or isinstance(e2e["exit_code"], bool)
        or e2e["exit_code"] != 0
        or e2e["conclusion"] != "success"
    ):
        raise ValidationError(f"jobs[{index}].e2e must be a successful pnpm e2e")
    quality = job["quality"]
    if not isinstance(quality, list) or not quality:
        raise ValidationError(f"jobs[{index}].quality must be a non-empty array")
    quality_names: set[str] = set()
    for quality_index, raw_command in enumerate(quality):
        command = _object(raw_command, f"jobs[{index}].quality[{quality_index}]")
        _required(command, ("command", "exit_code", "conclusion"))
        _no_unknown(
            command,
            {"command", "exit_code", "conclusion"},
            f"jobs[{index}].quality[{quality_index}]",
        )
        command_name = _string(command, "command")
        if command_name in quality_names:
            raise ValidationError(f"duplicate quality command: {command_name}")
        quality_names.add(command_name)
        if (
            isinstance(command["exit_code"], bool)
            or command["exit_code"] != 0
            or command["conclusion"] != "success"
        ):
            raise ValidationError(f"jobs[{index}].quality contains a non-success command")
    run_id = _string(job, "run_id")
    parsed_url = urlparse(_string(job, "url"))
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ValidationError(f"jobs[{index}].url must be an HTTPS URL")
    started = _strict_timestamp(job["started_at"], f"jobs[{index}].started_at")
    finished = _strict_timestamp(job["finished_at"], f"jobs[{index}].finished_at")
    if finished < started:
        raise ValidationError(f"jobs[{index}] finished_at precedes started_at")
    seen_paths: set[str] = set()
    for group in _HASH_GROUPS:
        _validate_hash_files(job[group], f"jobs[{index}].{group}", evidence_root, seen_paths)
    return platform, job_id, run_id


def validate_external_ci_evidence(
    data: Any,
    evidence_path: Path,
    repo_root: Path,
    candidate_path: Path,
    expected_source_commit: str,
) -> dict[str, Any]:
    """Validate a CI attestation and bind it to local candidate/workflow bytes."""

    evidence = _inside(evidence_path, repo_root, "external evidence")
    if not evidence.is_file():
        raise ValidationError("external evidence file is missing")
    item = _object(data, "external_ci_evidence")
    fields = {
        "schema_version",
        "source_commit",
        "candidate_id",
        "candidate_manifest_sha256",
        "workflow_sha256",
        "matrix",
        "jobs",
    }
    _required(item, tuple(fields))
    _no_unknown(item, fields, "external_ci_evidence")
    if item["schema_version"] != _SCHEMA_VERSION:
        raise ValidationError("external_ci_evidence.schema_version must be 1.0")
    source_commit = item["source_commit"]
    if not isinstance(source_commit, str) or not _COMMIT.fullmatch(source_commit):
        raise ValidationError("external_ci_evidence.source_commit is invalid")
    if source_commit != expected_source_commit:
        raise ValidationError("external CI source commit does not match checkout HEAD")
    candidate_id = item["candidate_id"]
    if not isinstance(candidate_id, str) or not _CANDIDATE.fullmatch(candidate_id):
        raise ValidationError("external_ci_evidence.candidate_id is invalid")
    for field in ("candidate_manifest_sha256", "workflow_sha256"):
        if not isinstance(item[field], str) or not _SHA256.fullmatch(item[field]):
            raise ValidationError(f"external_ci_evidence.{field} is invalid")
    matrix = item["matrix"]
    if matrix != ["windows", "ubuntu"]:
        raise ValidationError("external CI matrix must be exactly windows and ubuntu")
    candidate = _inside(candidate_path, repo_root, "candidate")
    if not candidate.is_file():
        raise ValidationError("candidate manifest is missing")
    try:
        candidate_data = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read candidate manifest: {exc}") from exc
    manifest = validate_candidate_manifest(candidate_data, candidate.parent)
    if manifest["candidate_id"] != candidate_id:
        raise ValidationError("external CI candidate_id does not match manifest")
    if manifest["source"]["commit"] != source_commit:
        raise ValidationError("candidate source commit does not match external CI evidence")
    if _sha256(candidate) != item["candidate_manifest_sha256"]:
        raise ValidationError("candidate manifest sha256 does not match evidence")
    workflow = _inside(repo_root / ".github/workflows/ci.yml", repo_root, "workflow")
    if not workflow.is_file() or _sha256(workflow) != item["workflow_sha256"]:
        raise ValidationError("workflow sha256 does not match checkout")
    jobs = item["jobs"]
    if not isinstance(jobs, list) or len(jobs) != 2:
        raise ValidationError("external CI evidence must contain exactly two jobs")
    seen_platforms: set[str] = set()
    seen_job_ids: set[str] = set()
    seen_run_ids: set[str] = set()
    for index, job in enumerate(jobs):
        platform, job_id, run_id = _validate_job(job, index, evidence.parent)
        if platform in seen_platforms:
            raise ValidationError(f"duplicate external CI platform: {platform}")
        if job_id in seen_job_ids or run_id in seen_run_ids:
            raise ValidationError("external CI job_id and run_id values must be unique")
        seen_platforms.add(platform)
        seen_job_ids.add(job_id)
        seen_run_ids.add(run_id)
    if seen_platforms != _PLATFORMS:
        raise ValidationError("external CI jobs must cover windows and ubuntu")
    return item
