"""Run the quality engine for one final MP4 and bind the result to a candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from uuid import UUID, uuid5

from workbench.quality.engine import QualityService
from workbench.quality.models import QualityReport, QualityTarget

NAMESPACE = UUID("7a7fa8f1-75bc-4df9-9d8b-a52de513ce09")


class CandidateQualityError(ValueError):
    """Raised when a candidate-bound quality input is invalid."""


def _load(path: Path, label: str) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise CandidateQualityError(f"{label}_invalid") from error
    if not isinstance(value, dict):
        raise CandidateQualityError(f"{label}_object_required")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _candidate(candidate_manifest: Path) -> tuple[str, str]:
    value = _load(candidate_manifest, "candidate_manifest")
    candidate_id = value.get("candidate_id")
    source = value.get("source")
    commit = source.get("git_commit") if isinstance(source, dict) else None
    if not isinstance(candidate_id, str) or not candidate_id.startswith("rc-"):
        raise CandidateQualityError("candidate_id_invalid")
    if value.get("status") not in {"candidate_frozen", "release_artifacts_ready"}:
        raise CandidateQualityError("candidate_not_frozen")
    if not isinstance(commit, str) or len(commit) != 40:
        raise CandidateQualityError("source_commit_invalid")
    return candidate_id, commit


def _prepend_tool_dir(tool_dir: Path | None) -> None:
    if tool_dir is None:
        return
    resolved = tool_dir.resolve()
    if not (resolved / "ffmpeg.exe").is_file() or not (resolved / "ffprobe.exe").is_file():
        raise CandidateQualityError("ffmpeg_runtime_missing")
    os.environ["PATH"] = str(resolved) + os.pathsep + os.environ.get("PATH", "")


def analyze_candidate(
    *,
    candidate_manifest: Path,
    video: Path,
    target_manifest: Path,
    output: Path,
    ffmpeg_dir: Path | None = None,
) -> dict[str, object]:
    candidate_id, source_commit = _candidate(candidate_manifest)
    video = video.resolve()
    if not video.is_file():
        raise CandidateQualityError("video_missing")
    _prepend_tool_dir(ffmpeg_dir)
    target_payload = _load(target_manifest, "target_manifest")
    target_payload["video_path"] = str(video)
    try:
        target = QualityTarget.model_validate(target_payload)
    except (TypeError, ValueError) as error:
        raise CandidateQualityError("target_manifest_invalid") from error
    project_default = uuid5(NAMESPACE, candidate_id + ":project")
    render_default = uuid5(NAMESPACE, candidate_id + ":" + video.name)
    project_id = UUID(str(target_payload.get("project_id", project_default)))
    render_job_id = UUID(str(target_payload.get("render_job_id", render_default)))
    report: QualityReport = QualityService().analyze(
        project_id=project_id,
        render_job_id=render_job_id,
        target=target,
        render_provenance={"candidate_id": candidate_id, "source_commit": source_commit},
    )
    report_payload = report.model_dump(mode="json")
    blocking_failures = sorted(
        {
            str(issue.get("code"))
            for issue in report_payload.get("issues", [])
            if isinstance(issue, dict) and str(issue.get("severity")) in {"P0", "P1"}
        }
    )
    status = (
        "passed"
        if not blocking_failures and report.result.value in {"pass", "pass_with_warnings"}
        else "blocked"
    )
    result: dict[str, object] = {
        "schema_version": "1.0",
        "stage": "P07_MEDIA_QUALITY",
        "status": status,
        "candidate_id": candidate_id,
        "source_commit": source_commit,
        "artifact": {
            "relative_path": video.name,
            "sha256": _sha256(video),
            "size": video.stat().st_size,
        },
        "blocking_failures": blocking_failures,
        "quality_report": report_payload,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-manifest", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--target-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ffmpeg-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        report = analyze_candidate(
            candidate_manifest=args.candidate_manifest,
            video=args.input,
            target_manifest=args.target_manifest,
            output=args.output,
            ffmpeg_dir=args.ffmpeg_dir,
        )
    except (CandidateQualityError, OSError, ValueError) as error:
        print(f"QUALITY_ACCEPTANCE=BLOCK reason={error}")
        return 1
    print(
        f"QUALITY_ACCEPTANCE={str(report['status']).upper()} "
        f"candidate_id={report['candidate_id']}"
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
