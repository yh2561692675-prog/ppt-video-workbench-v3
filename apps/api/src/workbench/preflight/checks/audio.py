from __future__ import annotations

from pathlib import Path

from workbench.domain.issues import IssueLevel, IssueLocation, PreflightIssue
from workbench.domain.models import ProjectManifest
from workbench.domain.presenter import PresentationMode

from .common import digest, issue


def fingerprint(project: ProjectManifest, root: Path) -> str:
    return digest(
        {
            "pages": [
                {
                    "id": str(page.id),
                    "audio": page.audio.model_dump(mode="json") if page.audio else None,
                }
                for page in project.pages
            ],
            "differences": [item.model_dump(mode="json") for item in project.audio_differences],
            "timeline": (
                project.audio_timeline.model_dump(mode="json") if project.audio_timeline else None
            ),
            "presentation_mode": project.presentation_mode,
            "presenter_source": (
                project.presenter_source.model_dump(mode="json")
                if project.presenter_source
                else None
            ),
            "presenter_timeline": (
                project.presenter_timeline.model_dump(mode="json")
                if project.presenter_timeline
                else None
            ),
            "root": str(root),
        }
    )


def check_audio(project: ProjectManifest, root: Path) -> tuple[str, list[PreflightIssue]]:
    check_fingerprint = fingerprint(project, root)
    if project.presentation_mode is PresentationMode.HUMAN_PRESENTER:
        return check_fingerprint, []
    issues: list[PreflightIssue] = []
    for page in project.pages:
        audio = page.audio
        if audio is None or not audio.relative_path or not (root / audio.relative_path).is_file():
            issues.append(
                issue(
                    project_id=project.id,
                    check="audio",
                    code="audio_missing",
                    level=IssueLevel.BLOCKING,
                    message=f"第{page.order}页没有有效音频文件",
                    action="完成本地录音分页或生成本页配音",
                    fingerprint=check_fingerprint,
                    location=IssueLocation(
                        page_id=page.id,
                        node="audio",
                        relative_path=audio.relative_path if audio else None,
                    ),
                )
            )
    pending = [item for item in project.audio_differences if item.status != "resolved"]
    if pending:
        for difference in pending:
            issues.append(
                issue(
                    project_id=project.id,
                    check="audio",
                    code="audio_difference_pending",
                    level=IssueLevel.CONFIRMATION,
                    message="音频与已确认旁白仍存在未处理差异",
                    action="接受录音、修改旁白或重新导入音频",
                    fingerprint=check_fingerprint,
                    location=IssueLocation(page_id=difference.page_id, node="audio-difference"),
                    blocking=False,
                )
            )
    if project.audio_timeline is None and not all(
        page.audio is not None
        and page.audio.relative_path
        and (root / page.audio.relative_path).is_file()
        for page in project.pages
    ):
        issues.append(
            issue(
                project_id=project.id,
                check="audio",
                code="timeline_missing",
                level=IssueLevel.BLOCKING,
                message="尚未生成页面音频时间轴",
                action="先完成音频转写与分页，再重新运行预检",
                fingerprint=check_fingerprint,
                location=IssueLocation(node="timeline"),
            )
        )
    return check_fingerprint, issues
