from __future__ import annotations

from pathlib import Path

from workbench.domain.issues import IssueLevel, IssueLocation, PreflightIssue
from workbench.domain.models import ProjectManifest

from .common import digest, issue


def fingerprint(project: ProjectManifest, root: Path) -> str:
    return digest(
        {
            "subtitle": (
                project.subtitle_artifact.model_dump(mode="json")
                if project.subtitle_artifact
                else None
            ),
            "preflight": (
                project.video_preflight.model_dump(mode="json") if project.video_preflight else None
            ),
            "root": str(root),
        }
    )


def check_video(project: ProjectManifest, root: Path) -> tuple[str, list[PreflightIssue]]:
    check_fingerprint = fingerprint(project, root)
    issues: list[PreflightIssue] = []
    artifact = project.subtitle_artifact
    if artifact is None:
        issues.append(
            issue(
                project_id=project.id,
                check="video",
                code="subtitle_missing",
                level=IssueLevel.BLOCKING,
                message="尚未生成字幕时间轴和 SRT",
                action="先完成字幕生成，再重新运行预检",
                fingerprint=check_fingerprint,
                location=IssueLocation(node="subtitle"),
            )
        )
    else:
        for path in (artifact.timeline_relative_path, artifact.srt_relative_path):
            if not (root / path).is_file():
                issues.append(
                    issue(
                        project_id=project.id,
                        check="video",
                        code="subtitle_artifact_missing",
                        level=IssueLevel.BLOCKING,
                        message="字幕产物文件不存在",
                        action="重新生成字幕时间轴和 SRT",
                        fingerprint=check_fingerprint,
                        location=IssueLocation(node="subtitle", relative_path=path),
                    )
                )
    if project.video_preflight is not None and not project.video_preflight.allowed:
        issues.append(
            issue(
                project_id=project.id,
                check="video",
                code="video_preview_failed",
                level=IssueLevel.BLOCKING,
                message="视频预览契约尚未通过",
                action="完成字幕、页面预览和字幕避让后重新预检",
                fingerprint=check_fingerprint,
                location=IssueLocation(node="video-preview"),
            )
        )
    return check_fingerprint, issues
