from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "2.0"
REQUIRED_PHASES = (
    "artifact_resolution",
    "clean_install",
    "candidate_identity",
    "first_launch",
    "second_launch",
    "legacy_project",
    "interruption_recovery",
    "full_preflight",
    "play_from_start",
    "final_export",
    "uninstall_reinstall",
    "reinstall_launch",
    "version_rollback",
    "process_cleanup",
    "workspace_retention",
)
INSTALL_PHASES = (
    "artifact_resolution",
    "clean_install",
    "candidate_identity",
    "first_launch",
    "second_launch",
    "uninstall_reinstall",
    "reinstall_launch",
    "process_cleanup",
    "workspace_retention",
)
REQUIRED_PHASE_FIELDS = (
    "result",
    "started_at",
    "finished_at",
    "duration_ms",
    "attempt",
    "reason_codes",
    "evidence_refs",
    "metrics",
)
SENSITIVE_KEY_NAMES = {
    "api_key",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
}
BEARER_PATTERN = re.compile(r"\bBearer\s+[^\s\"']+", re.IGNORECASE)
USER_PROFILE_PATTERN = re.compile(r"[A-Za-z]:\\Users\\[^\\/\"']+", re.IGNORECASE)
WORKSPACE_PATTERN = re.compile(r"[A-Za-z]:\\(?:[^\\/\"']+\\)*workspace-data", re.IGNORECASE)


def redact(value: object, *, key: str | None = None) -> object:
    """Return a structure that can safely be written into an acceptance report."""
    if key is not None and key.casefold() in SENSITIVE_KEY_NAMES:
        return "***"
    if isinstance(value, Mapping):
        return {
            str(item_key): redact(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        redacted = BEARER_PATTERN.sub("Bearer ***", value)
        redacted = USER_PROFILE_PATTERN.sub("%USERPROFILE%", redacted)
        return WORKSPACE_PATTERN.sub("%WORKBENCH_WORKSPACE%", redacted)
    return value


def _phase_errors(phases: object, phase_name: str) -> list[str]:
    if not isinstance(phases, Mapping):
        return ["phases_missing"]
    phase = phases.get(phase_name)
    if not isinstance(phase, Mapping):
        return ["phase_missing"]
    errors = [f"{field}_missing" for field in REQUIRED_PHASE_FIELDS if field not in phase]
    if phase.get("result") != "passed":
        errors.append("result_not_passed")
    if not isinstance(phase.get("duration_ms"), int) or phase.get("duration_ms", 0) < 0:
        errors.append("duration_ms_invalid")
    if not isinstance(phase.get("attempt"), int) or phase.get("attempt", 0) < 1:
        errors.append("attempt_invalid")
    if not isinstance(phase.get("reason_codes"), list):
        errors.append("reason_codes_invalid")
    if not isinstance(phase.get("evidence_refs"), list):
        errors.append("evidence_refs_invalid")
    if not isinstance(phase.get("metrics"), Mapping):
        errors.append("metrics_invalid")
    return list(dict.fromkeys(errors))


def required_phases(evidence: Mapping[str, object]) -> tuple[str, ...]:
    """Return the phases required by the declared acceptance scope."""

    scope = evidence.get("scope", "full")
    if scope == "install":
        return INSTALL_PHASES
    if scope == "full":
        return REQUIRED_PHASES
    return ("__invalid_scope__",)


def build_report(evidence: dict[str, object]) -> dict[str, object]:
    """Build the fixed schema 2.0 report and fail closed on incomplete evidence."""
    redacted = redact(evidence)
    if not isinstance(redacted, dict):
        raise TypeError("Redacted acceptance evidence must remain an object.")

    validation_errors: dict[str, list[str]] = {}
    if redacted.get("schema_version") != SCHEMA_VERSION:
        validation_errors["report"] = ["schema_version_invalid"]
    release = redacted.get("release")
    if not isinstance(release, Mapping) or not isinstance(release.get("candidate_id"), str):
        validation_errors["release"] = ["candidate_id_missing"]

    phases = redacted.get("phases")
    required = required_phases(redacted)
    if required == ("__invalid_scope__",):
        validation_errors["report"] = ["scope_invalid"]
    for phase_name in required:
        errors = _phase_errors(phases, phase_name)
        if errors:
            validation_errors[phase_name] = errors

    blocking_failures = list(validation_errors)
    return {
        "schema_version": SCHEMA_VERSION,
        "decision": "pass" if not blocking_failures else "block",
        "blocking_failures": blocking_failures,
        "validation_errors": validation_errors,
        "evidence": redacted,
    }


def _validate_evidence_references(
    evidence: Mapping[str, object], root: Path
) -> dict[str, list[str]]:
    phases = evidence.get("phases")
    if not isinstance(phases, Mapping):
        return {}
    root = root.resolve()
    failures: dict[str, list[str]] = {}
    for phase_name in required_phases(evidence):
        phase = phases.get(phase_name)
        if not isinstance(phase, Mapping):
            continue
        references = phase.get("evidence_refs")
        if not isinstance(references, list):
            continue
        for reference in references:
            if not isinstance(reference, str):
                failures.setdefault(phase_name, []).append("evidence_ref_invalid")
                continue
            candidate = (root / reference).resolve()
            if not candidate.is_relative_to(root):
                failures.setdefault(phase_name, []).append("evidence_ref_outside_root")
            elif not candidate.is_file():
                failures.setdefault(phase_name, []).append("evidence_ref_missing")
    return failures


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _render_html(report: Mapping[str, object]) -> str:
    decision = html.escape(str(report["decision"]))
    blockers = report["blocking_failures"]
    blocker_text = (
        ", ".join(str(item) for item in blockers) if isinstance(blockers, list) else "unknown"
    )
    encoded = html.escape(
        json.dumps(report["evidence"], ensure_ascii=False, indent=2, sort_keys=True)
    )
    validation = html.escape(
        json.dumps(report["validation_errors"], ensure_ascii=False, indent=2, sort_keys=True)
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        "<title>Windows Full Chain Acceptance</title></head><body>"
        f"<h1>Windows Full Chain Acceptance: {decision}</h1>"
        f"<p>Blocking failures: {html.escape(blocker_text or 'none')}</p>"
        f"<h2>Validation errors</h2><pre>{validation}</pre>"
        f"<h2>Evidence</h2><pre>{encoded}</pre></body></html>"
    )


def _write_evidence_manifest(output_dir: Path) -> None:
    artifacts = []
    for path in sorted(
        (output_dir / name for name in ("acceptance-report.json", "acceptance-report.html")),
        key=lambda item: item.name,
    ):
        artifacts.append(
            {
                "relative_path": path.name,
                "size": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    (output_dir / "evidence-manifest.json").write_text(
        json.dumps({"schema_version": SCHEMA_VERSION, "artifacts": artifacts}, indent=2) + "\n",
        encoding="utf-8",
    )


def write_report(evidence_path: Path, output_dir: Path) -> int:
    """Write JSON/HTML/manifest reports; return zero only for a complete pass."""
    loaded: Any = json.loads(evidence_path.read_text(encoding="utf-8-sig"))
    if not isinstance(loaded, dict):
        raise ValueError("Acceptance evidence must be a JSON object.")

    report = build_report(loaded)
    reference_errors = _validate_evidence_references(loaded, evidence_path.parent)
    if reference_errors:
        validation_errors = report["validation_errors"]
        if not isinstance(validation_errors, dict):
            raise TypeError("Acceptance validation errors must be an object.")
        for phase_name, errors in reference_errors.items():
            current = validation_errors.setdefault(phase_name, [])
            if isinstance(current, list):
                current.extend(error for error in errors if error not in current)
        report["blocking_failures"] = list(validation_errors)
        report["decision"] = "block"

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "acceptance-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output_dir / "acceptance-report.html").write_text(_render_html(report), encoding="utf-8")
    _write_evidence_manifest(output_dir)
    return 0 if report["decision"] == "pass" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Write a Windows full-chain acceptance report.")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    return write_report(args.evidence, args.output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
