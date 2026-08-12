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
from scripts.debug_program.release_preflight import resolve_iscc
from scripts.debug_program.runner import (
    CommandSpec,
    _safe_release_output,
    execute_command,
    full_automation_plan,
    new_run_id,
    recover_automation,
    release_output_root,
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


def test_runner_preserves_external_ci_block_as_blocked(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    candidate_id = "v1-rc-abc1234-20260811T193000Z"
    writer = EvidenceWriter(root, candidate_id, "run-dp20-001")
    verdict = run_plan(
        writer=writer,
        matrix="dp20-full",
        commands=(
            CommandSpec(
                "ci-wiring-check",
                (sys.executable, "-c", "raise SystemExit(2)"),
                tmp_path,
                {},
                30,
                (2,),
            ),
        ),
    )

    assert verdict["status"] == "blocked"
    assert verdict["first_failure"] is None
    assert verdict["commands"][0]["status"] == "failed"
    assert "external CI evidence is required" in verdict["notes"]
    validate_automation_verdict(verdict, writer.run_root)


def test_validator_rejects_unbound_blocked_verdicts(tmp_path: Path) -> None:
    result = tmp_path / "result.json"
    result.write_text("{}", encoding="utf-8")
    base = {
        "schema_version": "1.0",
        "candidate_id": "v1-rc-abc1234-20260811T193000Z",
        "run_id": "run-blocked-001",
        "matrix": "dp20-full",
        "status": "blocked",
        "started_at": "2026-08-11T19:30:00Z",
        "finished_at": "2026-08-11T19:30:01Z",
        "first_failure": None,
        "first_blocker": None,
    }

    with pytest.raises(ValidationError, match="blocked automation verdict"):
        validate_automation_verdict({**base, "commands": []}, tmp_path)

    with pytest.raises(ValidationError, match="blocked automation verdict"):
        validate_automation_verdict(
            {
                **base,
                "commands": [
                    {
                        "name": "ci-wiring-check",
                        "exit_code": 0,
                        "status": "passed",
                        "result": "result.json",
                    }
                ],
                "first_blocker": {
                    "name": "ci-wiring-check",
                    "exit_code": 2,
                    "result": "result.json",
                    "reason": "external CI evidence is required",
                },
            },
            tmp_path,
        )

    with pytest.raises(ValidationError, match="first_blocker must match"):
        validate_automation_verdict(
            {
                **base,
                "commands": [
                    {
                        "name": "ci-wiring-check",
                        "exit_code": 2,
                        "status": "failed",
                        "result": "result.json",
                        "blocked": True,
                    }
                ],
                "first_blocker": {
                    "name": "other-command",
                    "exit_code": 2,
                    "result": "result.json",
                    "reason": "external CI evidence is required",
                },
            },
            tmp_path,
        )

    blocker = {
        "name": "ci-wiring-check",
        "exit_code": 2,
        "result": "result.json",
        "reason": "external CI evidence is required",
    }
    for status, commands, failure in (
        (
            "passed",
            [{"name": "ok", "exit_code": 0, "status": "passed", "result": "result.json"}],
            None,
        ),
        (
            "failed",
            [{"name": "failed", "exit_code": 1, "status": "failed", "result": "result.json"}],
            {"name": "failed", "exit_code": 1, "result": "result.json"},
        ),
        ("interrupted", [], None),
    ):
        with pytest.raises(ValidationError, match="only blocked automation verdicts"):
            validate_automation_verdict(
                {
                    **base,
                    "status": status,
                    "commands": commands,
                    "first_failure": failure,
                    "first_blocker": blocker,
                },
                tmp_path,
            )


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
    assert len(first) <= 80
    assert "_" not in first


def test_release_preflight_resolves_user_local_iscc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local_app_data = tmp_path / "LocalAppData"
    iscc = local_app_data / "Programs" / "Inno Setup 6" / "ISCC.exe"
    iscc.parent.mkdir(parents=True)
    iscc.write_bytes(b"stub")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr("scripts.debug_program.release_preflight.shutil.which", lambda _: None)
    assert resolve_iscc() == iscc.resolve()


def test_candidate_runtime_probe_resolves_user_local_iscc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local_app_data = tmp_path / "LocalAppData"
    iscc = local_app_data / "Programs" / "Inno Setup 6" / "ISCC.exe"
    iscc.parent.mkdir(parents=True)
    iscc.write_bytes(b"stub")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setattr(candidate_module.shutil, "which", lambda _: None)
    assert candidate_module.resolve_iscc_path() == iscc.resolve()


def test_release_output_rejects_escape_and_absolute_paths(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="relative path"):
        _safe_release_output(tmp_path, "../outside")
    with pytest.raises(ValueError, match="relative path"):
        _safe_release_output(tmp_path, "C:/outside")
    with pytest.raises(ValueError, match="evidence root"):
        _safe_release_output(tmp_path, "dist/release")


def test_release_outputs_are_unique_and_run_specific(tmp_path: Path) -> None:
    candidate_id = "v1-rc-abc1234-20260811T193000Z"
    first_root = release_output_root(tmp_path, candidate_id, "run-first-001")
    second_root = release_output_root(tmp_path, candidate_id, "run-second-002")
    assert first_root != second_root
    first_plan = full_automation_plan(
        tmp_path, release_output_root=first_root
    )
    second_plan = full_automation_plan(
        tmp_path, release_output_root=second_root
    )
    first_build = next(item for item in first_plan if item.name == "release-build")
    second_build = next(item for item in second_plan if item.name == "release-build")
    assert first_build.argv != second_build.argv
    assert "release-payload" not in " ".join(first_build.argv)
    assert "release-artifacts" not in " ".join(first_build.argv)

    with pytest.raises(ValueError, match="relative path"):
        full_automation_plan(tmp_path, release_output_root="../outside")


def test_release_output_capture_records_artifact_hashes(tmp_path: Path) -> None:
    root = tmp_path / "test-results" / "debug-program" / "release" / "short-id"
    for relative in (
        "artifacts/release-artifacts.json",
        "artifacts/ppt-video-workbench-setup.exe",
        "payload/runtime-manifest.json",
        "payload/sbom/node-dependencies.json",
        "payload/sbom/python-dependencies.json",
        "payload/licenses/THIRD-PARTY-NOTICES.txt",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(relative.encode("utf-8"))
    result = execute_command(
        CommandSpec(
            "release-output-capture",
            (sys.executable, "-c", "pass"),
            tmp_path,
            {},
            30,
            release_output_root="test-results/debug-program/release/short-id",
        ),
        tmp_path / "evidence" / "commands",
        1,
    )
    assert result.status == "passed"
    record = json.loads(result.result.read_text(encoding="utf-8"))
    evidence = result.result.parent / record["release_output"]["path"]
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["relative_root"] == "test-results/debug-program/release/short-id"
    assert payload["aggregate_sha256"]
    assert {item["path"] for item in payload["files"]} >= {
        "artifacts/release-artifacts.json",
        "artifacts/ppt-video-workbench-setup.exe",
        "payload/runtime-manifest.json",
        "payload/sbom/node-dependencies.json",
        "payload/licenses/THIRD-PARTY-NOTICES.txt",
    }


def test_generated_run_id_is_accepted_by_verdict_validator(tmp_path: Path) -> None:
    run_id = new_run_id("v1-rc-abc1234-20260811T193000Z", "DP20_FULL")
    result = tmp_path / "result.json"
    result.write_text("{}", encoding="utf-8")
    validate_automation_verdict(
        {
            "schema_version": "1.0",
            "candidate_id": "v1-rc-abc1234-20260811T193000Z",
            "run_id": run_id,
            "matrix": "DP20_FULL",
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
    external_evidence = tmp_path / "external-ci-evidence.json"
    plan = full_automation_plan(
        tmp_path,
        release_output_root=release_output_root(
            tmp_path, "v1-rc-abc1234-20260811T193000Z", "run-plan-001"
        ),
        external_ci_evidence=external_evidence,
    )
    names = [item.name for item in plan]
    assert names[:6] == [
        "release-tool-preflight",
        "prepare-runtime",
        "release-input-preflight",
        "release-build",
        "python-full-tests",
        "python-ruff",
    ]
    assert "python-mypy" in names
    release_build = next(item for item in plan if item.name == "release-build")
    assert release_build.env["CI"] == "true"
    assert "root-lint" in names
    assert "root-tests" in names
    assert "export-contracts-check" in names
    assert "cloud-client-check" in names
    assert "ci-wiring-check" in names
    ci_wiring = next(item for item in plan if item.name == "ci-wiring-check")
    assert ci_wiring.argv[-2:] == (
        "--external-evidence",
        str(external_evidence.resolve()),
    )
    assert "contract-migration-regression" in names
    assert all(item.argv and item.argv[0] != "cmd.exe" for item in plan)
