from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.debug_program import ci_preflight
from scripts.debug_program.ci_evidence import validate_external_ci_evidence
from scripts.debug_program.models import ValidationError

COMMIT = "a" * 40
CANDIDATE_ID = "v1-rc-abc1234-20260811T193000Z"
REPOSITORY = "openai/ppt-video-workbench-v3"
QUALITY_COMMANDS = (
    "uv sync --frozen",
    "uv run ruff check .",
    "uv run mypy apps/api/src",
    "uv run pytest",
    "pnpm install --frozen-lockfile",
    "pnpm check",
)
WORKFLOW = """name: CI
jobs:
  quality:
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
    steps:
      - run: pnpm e2e
"""


def _write_ref(root: Path, relative: str, content: bytes) -> dict[str, Any]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return {
        "path": relative,
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _fixture(tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    workflow_path = repo_root / ".github/workflows/ci.yml"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text(WORKFLOW, encoding="utf-8")

    candidate_root = repo_root / "candidate"
    candidate_root.mkdir()
    payload = _write_ref(candidate_root, "payload.txt", b"candidate payload")
    manifest = {
        "schema_version": "1.0",
        "candidate_id": CANDIDATE_ID,
        "generated_at": "2026-08-11T19:30:00Z",
        "source": {"commit": COMMIT, "branch": "codex/test", "dirty": False},
        "files": [payload],
    }
    candidate_path = candidate_root / "candidate-manifest.json"
    candidate_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    evidence_path = repo_root / "external-ci-evidence.json"
    jobs: list[dict[str, Any]] = []
    for platform in ("windows", "ubuntu"):
        job_id = "1001" if platform == "windows" else "1002"
        jobs.append(
            {
                "platform": platform,
                "job_id": job_id,
                "conclusion": "success",
                "e2e": {"command": "pnpm e2e", "exit_code": 0, "conclusion": "success"},
                "quality": [
                    {"command": command, "exit_code": 0, "conclusion": "success"}
                    for command in QUALITY_COMMANDS
                ],
                "provider": "github-actions",
                "repository": REPOSITORY,
                "run_id": "123456789",
                "workflow_run_url": (
                    "https://github.com/openai/ppt-video-workbench-v3/actions/runs/123456789"
                ),
                "job_url": (
                    "https://github.com/openai/ppt-video-workbench-v3/actions/runs/123456789"
                    f"/job/{job_id}"
                ),
                "started_at": "2026-08-11T20:00:00Z",
                "finished_at": "2026-08-11T20:05:00Z",
                "artifacts": [
                    _write_ref(repo_root, f"evidence/{platform}-artifact.bin", b"artifact")
                ],
                "logs": [_write_ref(repo_root, f"evidence/{platform}-log.txt", b"log")],
                "reports": [_write_ref(repo_root, f"evidence/{platform}-report.json", b"{}")],
                "traces": [_write_ref(repo_root, f"evidence/{platform}-trace.zip", b"trace")],
            }
        )
    evidence = {
        "schema_version": "1.0",
        "source_commit": COMMIT,
        "candidate_id": CANDIDATE_ID,
        "candidate_manifest_sha256": hashlib.sha256(candidate_path.read_bytes()).hexdigest(),
        "workflow_sha256": hashlib.sha256(workflow_path.read_bytes()).hexdigest(),
        "matrix": ["windows", "ubuntu"],
        "jobs": jobs,
    }
    evidence_path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return repo_root, candidate_path, evidence


def test_external_ci_golden_and_cli_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_root, candidate_path, evidence = _fixture(tmp_path)
    evidence_path = repo_root / "external-ci-evidence.json"
    monkeypatch.setattr(ci_preflight, "_git_head", lambda _: COMMIT)
    monkeypatch.setattr(ci_preflight, "_git_origin_repository", lambda _: REPOSITORY)
    assert (
        validate_external_ci_evidence(
            evidence, evidence_path, repo_root, candidate_path, COMMIT, REPOSITORY
        )["candidate_id"]
        == CANDIDATE_ID
    )
    assert (
        ci_preflight.main(
            [
                "--repo-root",
                str(repo_root),
                "--candidate",
                str(candidate_path),
                "--external-evidence",
                str(evidence_path),
            ]
        )
        == 0
    )


def test_ci_preflight_without_external_evidence_is_blocked(tmp_path: Path) -> None:
    repo_root, _, _ = _fixture(tmp_path)
    assert ci_preflight.main(["--repo-root", str(repo_root)]) == 2


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        ("https://github.com/OpenAI/ppt-video-workbench-v3.git", REPOSITORY),
        ("git@github.com:OpenAI/ppt-video-workbench-v3.git", REPOSITORY),
        ("ssh://git@github.com/OpenAI/ppt-video-workbench-v3.git", REPOSITORY),
    ],
)
def test_github_origin_parsing_accepts_https_and_ssh(remote: str, expected: str) -> None:
    assert ci_preflight._parse_github_origin(remote) == expected


@pytest.mark.parametrize(
    "remote",
    [
        "",
        "https://gitlab.com/openai/ppt-video-workbench-v3.git",
        "https://github.com/openai/ppt-video-workbench-v3/extra.git",
        "https://github.com/openai/ppt-video-workbench-v3?mirror=1",
        "ssh://user@github.com/openai/ppt-video-workbench-v3.git",
    ],
)
def test_github_origin_parsing_rejects_missing_non_github_and_weird_paths(
    remote: str,
) -> None:
    with pytest.raises(ValidationError):
        ci_preflight._parse_github_origin(remote)


@pytest.mark.parametrize(
    "stdout",
    ["", "https://gitlab.com/openai/ppt-video-workbench-v3.git", "https://github.com/a/b\nhttps://github.com/c/d"],
)
def test_git_origin_repository_requires_one_trusted_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stdout: str
) -> None:
    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args[0], 0, stdout=stdout, stderr="")

    monkeypatch.setattr(ci_preflight.subprocess, "run", fake_run)
    with pytest.raises(ValidationError):
        ci_preflight._git_origin_repository(tmp_path)


def test_ci_preflight_blocks_without_trusted_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo_root, candidate_path, _ = _fixture(tmp_path)
    evidence_path = repo_root / "external-ci-evidence.json"

    def missing_origin(_: Path) -> str:
        raise ValidationError("trusted GitHub origin is unavailable")

    monkeypatch.setattr(ci_preflight, "_git_origin_repository", missing_origin)
    assert (
        ci_preflight.main(
            [
                "--repo-root",
                str(repo_root),
                "--candidate",
                str(candidate_path),
                "--external-evidence",
                str(evidence_path),
            ]
        )
        == 2
    )
    assert "trusted GitHub origin unavailable" in capsys.readouterr().out


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"unknown": True}),
        lambda value: value.update({"source_commit": "b" * 40}),
        lambda value: value.update({"candidate_id": "v1-rc-other-20260811T193000Z"}),
        lambda value: value.update({"candidate_manifest_sha256": "0" * 64}),
        lambda value: value.update({"workflow_sha256": "0" * 64}),
        lambda value: value.update({"matrix": ["windows", "windows"]}),
        lambda value: value["jobs"].__setitem__(0, copy.deepcopy(value["jobs"][1])),
        lambda value: value["jobs"][0]["e2e"].update({"conclusion": "skipped"}),
        lambda value: value["jobs"][0].update({"continue-on-error": True}),
        lambda value: value["jobs"][0].update({"timeout": True}),
        lambda value: value["jobs"][0].update({"cancelled": True}),
        lambda value: value["jobs"][0]["quality"][0].update({"command": "echo ok"}),
        lambda value: value["jobs"][0]["quality"].pop(),
        lambda value: value["jobs"][0]["quality"][1].update(
            {"command": value["jobs"][0]["quality"][0]["command"]}
        ),
        lambda value: value["jobs"][0]["quality"].append(
            copy.deepcopy(value["jobs"][0]["quality"][0])
        ),
        lambda value: value["jobs"][0]["quality"][0].update({"exit_code": 1}),
        lambda value: value["jobs"][0]["artifacts"][0].update({"extra": True}),
        lambda value: value["jobs"][0]["artifacts"][0].update({"sha256": "0" * 64}),
        lambda value: value["jobs"][0]["logs"][0].update({"path": "../outside.txt"}),
        lambda value: value["jobs"][0]["reports"][0].update({"path": "C:/outside.json"}),
        lambda value: value["jobs"][1]["artifacts"].__setitem__(
            0, copy.deepcopy(value["jobs"][0]["artifacts"][0])
        ),
        lambda value: value["jobs"][1].update({"job_url": value["jobs"][0]["job_url"]}),
        lambda value: value["jobs"][1].update({"job_url": "https://evil.example/runs/1/job/2"}),
        lambda value: value["jobs"][0].update({"repository": "other/project"}),
        lambda value: value["jobs"][0].update({"run_id": "run-123"}),
        lambda value: value["jobs"][0].update({"job_id": "job-1001"}),
    ],
)
def test_external_ci_invalid_variants_are_rejected(
    tmp_path: Path, mutate: Any
) -> None:
    repo_root, candidate_path, evidence = _fixture(tmp_path)
    evidence_path = repo_root / "external-ci-evidence.json"
    value = copy.deepcopy(evidence)
    mutate(value)
    with pytest.raises(ValidationError):
        validate_external_ci_evidence(
            value, evidence_path, repo_root, candidate_path, COMMIT, REPOSITORY
        )


def test_ci_preflight_rejects_evidence_without_candidate(tmp_path: Path) -> None:
    repo_root, _, _ = _fixture(tmp_path)
    evidence_path = repo_root / "external-ci-evidence.json"
    assert (
        ci_preflight.main(
            ["--repo-root", str(repo_root), "--external-evidence", str(evidence_path)]
        )
        == 2
    )
