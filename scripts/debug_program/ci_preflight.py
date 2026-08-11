"""Check CI wiring and require evidence from an external runner for DP24."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import urlparse

from .ci_evidence import validate_external_ci_evidence
from .models import ValidationError

_REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_SSH_SCHEME = re.compile(r"^git@github\.com:([^/]+)/([^/]+)$")
_SCP_REPOSITORY = re.compile(r"^/([^/]+)/([^/]+)$")


def _git_head(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValidationError(f"cannot read checkout HEAD: {exc}") from exc
    head = completed.stdout.strip()
    if len(head) != 40 or any(char not in "0123456789abcdef" for char in head):
        raise ValidationError("checkout HEAD is not a 40-character lowercase commit")
    return head


def _repository_from_path(path: str) -> str:
    if path.endswith("/"):
        raise ValidationError("GitHub origin has a trailing path separator")
    match = _SCP_REPOSITORY.fullmatch(path)
    if match is None:
        raise ValidationError("GitHub origin must contain exactly owner/repository")
    owner, repository = match.groups()
    if repository.endswith(".git"):
        repository = repository[:-4]
    value = f"{owner}/{repository}".lower()
    if not _REPOSITORY.fullmatch(value):
        raise ValidationError("GitHub origin owner/repository is invalid")
    return value


def _parse_github_origin(remote: str) -> str:
    value = remote.strip()
    if not value:
        raise ValidationError("GitHub origin is empty")
    scp_match = _SSH_SCHEME.fullmatch(value)
    if scp_match is not None:
        return _repository_from_path(f"/{scp_match.group(1)}/{scp_match.group(2)}")
    try:
        parsed = urlparse(value)
    except ValueError as exc:
        raise ValidationError("GitHub origin URL is malformed") from exc
    if parsed.scheme not in {"https", "ssh"}:
        raise ValidationError("Git origin must use GitHub HTTPS or SSH")
    if parsed.hostname != "github.com" or parsed.query or parsed.fragment:
        raise ValidationError("Git origin must be github.com without query or fragment")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValidationError("GitHub origin port is invalid") from exc
    if port is not None:
        raise ValidationError("GitHub origin must not specify a port")
    if parsed.scheme == "ssh" and parsed.username != "git":
        raise ValidationError("GitHub SSH origin must use the git user")
    if parsed.scheme == "https" and parsed.netloc != "github.com":
        raise ValidationError("GitHub HTTPS origin must not include credentials")
    if parsed.scheme == "ssh" and parsed.netloc != "git@github.com":
        raise ValidationError("GitHub SSH origin must use git@github.com")
    return _repository_from_path(parsed.path)


def _git_origin_repository(repo_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "remote", "get-url", "--all", "origin"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValidationError("trusted GitHub origin is unavailable") from exc
    remotes = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    if len(remotes) != 1:
        raise ValidationError("trusted GitHub origin must have exactly one origin URL")
    return _parse_github_origin(remotes[0])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument(
        "--candidate",
        type=Path,
        help="candidate-manifest.json bound to the external CI attestation",
    )
    parser.add_argument(
        "--external-evidence",
        type=Path,
        help="validated evidence emitted by a completed Windows/Ubuntu CI matrix",
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    try:
        workflow_path = repo_root / ".github/workflows/ci.yml"
        workflow = workflow_path.read_text(encoding="utf-8")
    except OSError as exc:
        payload = {
            "schema_version": "1.0",
            "status": "blocked",
            "checks": {},
            "external_runner": f"cannot read CI workflow: {exc}",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    checks = {
        "ubuntu_and_windows_matrix": "ubuntu-latest" in workflow and "windows-latest" in workflow,
        "explicit_pnpm_e2e": "pnpm e2e" in workflow,
        "no_continue_on_error": "continue-on-error" not in workflow,
    }
    external_runner = "not executed locally; CI evidence remains required"
    if args.external_evidence is not None:
        try:
            expected_repository = _git_origin_repository(repo_root)
        except ValidationError as exc:
            external_runner = f"trusted GitHub origin unavailable: {exc}"
            checks["trusted_repository"] = False
        else:
            if args.candidate is None:
                external_runner = "candidate is required when external CI evidence is supplied"
            else:
                evidence = args.external_evidence.resolve()
                candidate = args.candidate.resolve()
                if not evidence.is_file() or not evidence.is_relative_to(repo_root):
                    external_runner = "external evidence path is missing or outside repo-root"
                else:
                    try:
                        raw = json.loads(evidence.read_text(encoding="utf-8"))
                        validated = validate_external_ci_evidence(
                            raw,
                            evidence,
                            repo_root,
                            candidate,
                            _git_head(repo_root),
                            expected_repository,
                        )
                        relative = evidence.relative_to(repo_root).as_posix()
                        external_runner = f"validated external evidence: {relative}"
                        checks["external_evidence_schema"] = True
                        checks["external_evidence_candidate"] = bool(validated["candidate_id"])
                        checks["trusted_repository"] = True
                    except (OSError, json.JSONDecodeError, ValidationError) as exc:
                        external_runner = f"external evidence rejected: {exc}"
                        checks["external_evidence_schema"] = False
    checks["external_runner_evidence"] = external_runner.startswith("validated external evidence:")
    payload = {
        "schema_version": "1.0",
        "status": "passed" if all(checks.values()) else "blocked",
        "checks": checks,
        "external_runner": external_runner,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
