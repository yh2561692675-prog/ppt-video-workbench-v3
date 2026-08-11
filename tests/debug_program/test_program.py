from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from scripts.debug_program import candidate as candidate_module
from scripts.debug_program.evidence import EvidenceWriter
from scripts.debug_program.isolation import IsolatedRun
from scripts.debug_program.models import (
    ValidationError,
    validate_automation_verdict,
    validate_candidate_manifest,
    validate_defect,
    validate_run,
    validate_scenario,
    validate_signoff,
)
from scripts.debug_program.registry import list_scenarios
from scripts.debug_program.runner import (
    CommandSpec,
    execute_command,
    full_automation_plan,
    new_run_id,
    recover_automation,
    run_plan,
)


def candidate(tmp_path: Path) -> dict[str, object]:
    payload = tmp_path / "payload.txt"
    payload.write_text("payload", encoding="utf-8")
    return {
        "schema_version": "1.0",
        "candidate_id": "v1-rc-abc1234-20260811T193000Z",
        "generated_at": "2026-08-11T19:30:00Z",
        "source": {"commit": "a" * 40, "branch": "codex/test", "dirty": False},
        "files": [
            {
                "path": "payload.txt",
                "size": payload.stat().st_size,
                "sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
            }
        ],
    }


def test_candidate_manifest_rejects_dirty_or_escape(tmp_path: Path) -> None:
    value = candidate(tmp_path)
    validate_candidate_manifest(value, tmp_path)
    value["source"] = {"commit": "a" * 40, "branch": "codex/test", "dirty": True}
    with pytest.raises(ValidationError, match="dirty"):
        validate_candidate_manifest(value)
    value = candidate(tmp_path)
    value["files"] = [{"path": "../payload.txt", "size": 1, "sha256": "0" * 64}]
    with pytest.raises(ValidationError, match="inside"):
        validate_candidate_manifest(value)


def test_contract_validators_cover_scenario_run_defect_signoff() -> None:
    scenario = list_scenarios(matrix="local-e2e")[0]
    validate_scenario(scenario)
    validate_run(
        {
            "schema_version": "1.0",
            "run_id": "run-local-e2e-001",
            "candidate_id": "v1-rc-abc1234-20260811T193000Z",
            "matrix": "local-e2e",
            "started_at": "2026-08-11T19:30:01Z",
            "attempt": 1,
            "status": "planned",
            "artifacts": [],
            "orphan_processes": [],
        }
    )
    candidate_id = "v1-rc-abc1234-20260811T193000Z"
    validate_defect(
        {
            "schema_version": "1.0",
            "defect_id": "DEF-v1-rc-abc1234-001",
            "severity": "P1",
            "owner": "A",
            "title": "example",
            "reproduction": "run fixture",
            "status": "open",
            "candidate_id": candidate_id,
        }
    )
    validate_signoff(
        {
            "schema_version": "1.0",
            "candidate_id": candidate_id,
            "role": "product",
            "reviewer": "test",
            "decision": "blocked",
            "signed_at": "2026-08-11T19:30:01Z",
            "evidence_hashes": ["0" * 64],
        }
    )


def test_evidence_writer_is_append_only_and_recovers(tmp_path: Path) -> None:
    writer = EvidenceWriter(
        tmp_path / "evidence", "v1-rc-abc1234-20260811T193000Z", "run-local-e2e-001"
    )
    writer.create_run("local-e2e")
    _, first = writer.start_attempt("DBG-recovery-001")
    writer.finish_attempt(first, status="failed", notes=["first attempt is retained"])
    _, second = writer.start_attempt("DBG-recovery-001")
    recovered = writer.recover_interrupted()
    assert recovered == [second / "interrupted.json"]
    with pytest.raises(FileExistsError):
        writer.finish_attempt(first, status="passed")
    manifest = writer.manifest()
    assert json.loads(manifest.read_text(encoding="utf-8"))["files"]


def test_isolation_owns_paths_and_ports(tmp_path: Path) -> None:
    root = tmp_path / "runs"
    with IsolatedRun(
        root, "v1-rc-abc1234-20260811T193000Z", "run-local-e2e-001", requested_ports=1
    ) as run:
        assert len(run.ports) == 1
        assert run.path("workspace/input.txt").parent == run.workspace
        with pytest.raises(ValueError):
            run.path("../outside.txt")
    assert (
        root / "v1-rc-abc1234-20260811T193000Z" / "run-local-e2e-001" / "environment.json"
    ).exists()


def test_registry_restricts_destructive_and_paid_by_default() -> None:
    safe = list_scenarios()
    assert {item["scenario_id"] for item in safe} == {"DBG-core-001", "DBG-recovery-001"}
    release = list_scenarios(matrix="release", include_restricted=True)
    assert release[0]["destructive"] is True


def test_runner_executes_and_preserves_first_failure(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    candidate_id = "v1-rc-abc1234-20260811T193000Z"
    writer = EvidenceWriter(root, candidate_id, "run-python-smoke-001")
    commands = (
        CommandSpec(
            "first-failure",
            ("python", "-c", "import sys; print('first failure'); sys.exit(7)"),
            tmp_path,
            {},
            30,
        ),
        CommandSpec("must-not-run", ("python", "-c", "raise SystemExit(8)"), tmp_path, {}, 30),
    )
    verdict = run_plan(writer=writer, matrix="python-smoke", commands=commands)
    assert verdict["status"] == "failed"
    assert verdict["first_failure"]["exit_code"] == 7
    assert len(verdict["commands"]) == 1
    result = (
        root
        / candidate_id
        / "run-python-smoke-001"
        / "commands"
        / "001-first-failure"
        / "result.json"
    )
    assert json.loads(result.read_text(encoding="utf-8"))["exit_code"] == 7


def test_runner_rejects_empty_plan_without_creating_a_passed_run(tmp_path: Path) -> None:
    writer = EvidenceWriter(
        tmp_path / "evidence", "v1-rc-abc1234-20260811T193000Z", "run-empty-001"
    )
    with pytest.raises(ValueError, match="at least one"):
        run_plan(writer=writer, matrix="python-smoke", commands=())
    assert not (writer.run_root / "run.json").exists()


def test_runner_closes_logs_and_rejects_empty_command_name(tmp_path: Path) -> None:
    output = tmp_path / "commands"
    result = execute_command(
        CommandSpec("log-close", (sys.executable, "-c", "print('ok')"), tmp_path, {}, 30),
        output,
        1,
    )
    renamed = result.stdout.with_name("stdout-renamed.log")
    result.stdout.rename(renamed)
    assert renamed.read_text(encoding="utf-8").strip() == "ok"
    with pytest.raises(ValueError, match="command name"):
        execute_command(CommandSpec("!!!", (sys.executable, "-c", "pass"), tmp_path, {}), output, 2)


def test_runner_records_timeout_and_spawn_errors(tmp_path: Path) -> None:
    timeout = execute_command(
        CommandSpec(
            "timeout",
            (sys.executable, "-c", "import time; time.sleep(0.1)"),
            tmp_path,
            {},
            0,
        ),
        tmp_path / "commands",
        1,
    )
    assert timeout.exit_code == 124
    missing = execute_command(
        CommandSpec("spawn-error", ("definitely-not-an-executable",), tmp_path, {}),
        tmp_path / "commands",
        2,
    )
    assert missing.exit_code == 127


def test_automation_verdict_is_validated_and_recovery_is_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    writer = EvidenceWriter(root, "v1-rc-abc1234-20260811T193000Z", "run-recovery-001")
    writer.create_run("python-smoke", status="running")
    first = recover_automation(writer)
    second = recover_automation(writer)
    assert first is not None
    assert second is None
    verdict = json.loads(first.read_text(encoding="utf-8"))
    validate_automation_verdict(verdict, writer.run_root)
    verdict["unexpected"] = True
    with pytest.raises(ValidationError, match="unknown fields"):
        validate_automation_verdict(verdict)

    result = writer.run_root / "result.json"
    result.write_text("{}", encoding="utf-8")
    base = {
        "schema_version": "1.0",
        "candidate_id": writer.candidate_id,
        "run_id": writer.run_id,
        "matrix": "python-smoke",
        "started_at": "2026-08-11T19:30:00Z",
        "finished_at": "2026-08-11T19:30:01Z",
        "commands": [],
        "first_failure": None,
    }
    with pytest.raises(ValidationError, match="all commands"):
        validate_automation_verdict({**base, "status": "passed"}, writer.run_root)
    failed = {
        **base,
        "status": "failed",
        "commands": [{"name": "x", "exit_code": 7, "status": "failed", "result": "result.json"}],
        "first_failure": {"name": "wrong", "exit_code": 7, "result": "result.json"},
    }
    with pytest.raises(ValidationError, match="first_failure"):
        validate_automation_verdict(failed, writer.run_root)


def test_candidate_checkout_binding_rejects_mismatch_and_dirty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    value = candidate(tmp_path)

    def fake_git(_root: Path, *args: str) -> str:
        if args == ("rev-parse", "--show-toplevel"):
            return str(tmp_path)
        if args == ("rev-parse", "HEAD"):
            return "a" * 40
        return ""

    monkeypatch.setattr(candidate_module, "_git", fake_git)
    candidate_module.validate_checkout(value, tmp_path)
    value["source"] = {"commit": "b" * 40, "branch": "codex/test", "dirty": False}
    with pytest.raises(ValidationError, match="HEAD"):
        candidate_module.validate_checkout(value, tmp_path)

    value["source"] = {"commit": "a" * 40, "branch": "codex/test", "dirty": False}
    def dirty_git(_root: Path, *args: str) -> str:
        if args[0] == "status":
            return " M source.py"
        if args[-1] == "--show-toplevel":
            return str(tmp_path)
        return "a" * 40

    monkeypatch.setattr(candidate_module, "_git", dirty_git)
    with pytest.raises(ValidationError, match="dirty"):
        candidate_module.validate_checkout(value, tmp_path)


def test_candidate_rejects_untracked_checkout_and_missing_snapshot_cleans_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def clean_or_untracked(_root: Path, *args: str) -> str:
        if args[0] == "status":
            return "?? new-source.py"
        if args[-1] == "--show-toplevel":
            return str(tmp_path)
        return "a" * 40

    monkeypatch.setattr(candidate_module, "_git", clean_or_untracked)
    with pytest.raises(RuntimeError, match="dirty"):
        candidate_module.build_candidate(tmp_path, tmp_path / "candidates")
    assert not (tmp_path / "candidates").exists()

    def clean_git(_root: Path, *args: str) -> str:
        if args[0] == "status":
            return ""
        if args[-1] == "--show-toplevel":
            return str(tmp_path)
        if args[-1] == "HEAD":
            return "a" * 40
        return "codex/test"

    monkeypatch.setattr(candidate_module, "_git", clean_git)
    monkeypatch.setattr(candidate_module, "SNAPSHOT_FILES", ("missing-lock.yaml",))
    output = tmp_path / "candidates"
    with pytest.raises(RuntimeError, match="snapshot files"):
        candidate_module.build_candidate(tmp_path, output)
    assert not any(output.iterdir())


def test_run_ids_are_unique_within_one_second() -> None:
    first = new_run_id("v1-rc-abc1234-20260811T193000Z", "python-smoke")
    second = new_run_id("v1-rc-abc1234-20260811T193000Z", "python-smoke")
    assert first != second
    assert "T" not in first and "Z" not in first


def test_generated_run_id_is_accepted_by_verdict_validator(tmp_path: Path) -> None:
    run_id = new_run_id("v1-rc-abc1234-20260811T193000Z", "python-smoke")
    result = tmp_path / "result.json"
    result.write_text("{}", encoding="utf-8")
    validate_automation_verdict(
        {
            "schema_version": "1.0",
            "candidate_id": "v1-rc-abc1234-20260811T193000Z",
            "run_id": run_id,
            "matrix": "python-smoke",
            "status": "passed",
            "started_at": "2026-08-11T19:30:00Z",
            "finished_at": "2026-08-11T19:30:01Z",
            "commands": [
                {"name": "smoke", "exit_code": 0, "status": "passed", "result": "result.json"}
            ],
            "first_failure": None,
        },
        tmp_path,
    )


def test_full_automation_plan_is_explicit_and_sequential(tmp_path: Path) -> None:
    plan = full_automation_plan(tmp_path)
    names = [item.name for item in plan]
    assert names[:3] == ["python-full-tests", "python-ruff", "python-mypy"]
    assert "web-tests" in names
    assert "remotion-tests" in names
    assert "contract-migration-regression" in names
    assert all(item.argv and item.argv[0] != "cmd.exe" for item in plan)
