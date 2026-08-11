from __future__ import annotations

import shutil
from pathlib import Path
from uuid import UUID

from workbench.domain.issues import IssueLevel, IssueLocation, IssueTimeRange, PreflightIssue
from workbench.domain.models import ProjectManifest
from workbench.domain.presenter import PresentationMode

from .common import digest, issue

WARNING_DETAILS = {
    "PRESENTER_LOW_RESOLUTION": (
        "真人视频分辨率低于建议值",
        "建议使用至少 1280×720 的源视频，或确认继续使用当前素材",
    ),
    "PRESENTER_LOW_VOLUME": (
        "真人原声音量偏低",
        "调整录音电平或确认后继续",
    ),
    "PRESENTER_LONG_SILENCE": (
        "真人原声包含较长静音",
        "复核静音区间是否为有效停顿",
    ),
    "PRESENTER_VARIABLE_FPS": (
        "真人视频使用可变帧率",
        "正式渲染前确认音画同步，必要时转换为恒定帧率",
    ),
}


def check_presenter_source(
    project: ProjectManifest,
    root: Path,
) -> tuple[str, list[PreflightIssue]]:
    source = project.presenter_source
    check_fingerprint = digest(
        {
            "mode": project.presentation_mode,
            "source": source.model_dump(mode="json") if source else None,
            "timeline": (
                project.presenter_timeline.model_dump(mode="json")
                if project.presenter_timeline
                else None
            ),
            "root": str(root),
        }
    )
    if project.presentation_mode is PresentationMode.AI_NARRATION:
        return check_fingerprint, []
    if source is None:
        return check_fingerprint, [
            _issue(
                project,
                "PRESENTER_SOURCE_MISSING",
                IssueLevel.BLOCKING,
                "真人讲解模式尚未导入视频",
                "导入包含有效原声音轨的 MP4 或 MOV 文件",
                check_fingerprint,
            )
        ]

    path = root / source.relative_path
    issues: list[PreflightIssue] = []
    if not path.is_file():
        issues.append(
            _issue(
                project,
                "PRESENTER_SOURCE_MISSING",
                IssueLevel.BLOCKING,
                "真人讲解源视频不存在",
                "重新导入真人讲解视频",
                check_fingerprint,
                source.relative_path,
            )
        )
        return check_fingerprint, issues

    required_free = max(path.stat().st_size * 3, 64 * 1024 * 1024)
    if shutil.disk_usage(root).free < required_free:
        issues.append(
            _issue(
                project,
                "PRESENTER_DISK_INSUFFICIENT",
                IssueLevel.BLOCKING,
                "可用空间不足以处理真人视频",
                "释放空间或更换工作目录后重试",
                check_fingerprint,
                source.relative_path,
            )
        )
    warnings = source.probe_snapshot.get("warnings", [])
    if isinstance(warnings, list):
        for code in warnings:
            details = WARNING_DETAILS.get(str(code))
            if details is None:
                continue
            issues.append(
                _issue(
                    project,
                    str(code),
                    IssueLevel.REQUIRED_WARNING,
                    details[0],
                    details[1],
                    check_fingerprint,
                    source.relative_path,
                    blocking=False,
                )
            )
    timeline = project.presenter_timeline
    if timeline is None:
        issues.append(
            _issue(
                project,
                "PRESENTER_TIMELINE_MISSING",
                IssueLevel.BLOCKING,
                "真人视频尚未生成可渲染时间线",
                "完成识别、页面匹配与时间线生成后重新预检",
                check_fingerprint,
                source.relative_path,
                reason="timeline_not_generated",
                time_range=IssueTimeRange(start_ms=0, end_ms=source.duration_ms),
            )
        )
        return check_fingerprint, issues
    if timeline.source_id != source.id or timeline.source_version != source.sha256:
        issues.append(
            _issue(
                project,
                "PRESENTER_TIMELINE_STALE",
                IssueLevel.BLOCKING,
                "真人时间线与当前源视频版本不一致",
                "保留人工锁定后重新识别并局部重算时间线",
                check_fingerprint,
                source.relative_path,
                reason="source_version_mismatch",
                time_range=IssueTimeRange(start_ms=0, end_ms=source.duration_ms),
            )
        )
    for anchor in timeline.anchors:
        if anchor.status not in {"blocked", "review"}:
            continue
        issues.append(
            _issue(
                project,
                "PRESENTER_ANCHOR_BLOCKED"
                if anchor.status == "blocked"
                else "PRESENTER_ANCHOR_REVIEW",
                IssueLevel.BLOCKING if anchor.status == "blocked" else IssueLevel.REQUIRED_WARNING,
                "页面锚点置信度过低" if anchor.status == "blocked" else "页面锚点需要人工复核",
                "在真人讲解工作台校正页码和时间边界并锁定",
                check_fingerprint,
                source.relative_path,
                page_id=anchor.page_id,
                reason=f"confidence:{anchor.confidence:.4f}",
                time_range=IssueTimeRange(start_ms=anchor.start_ms, end_ms=anchor.end_ms),
                blocking=anchor.status == "blocked",
            )
        )
    return check_fingerprint, issues


def _issue(
    project: ProjectManifest,
    code: str,
    level: IssueLevel,
    message: str,
    action: str,
    fingerprint: str,
    relative_path: str | None = None,
    *,
    page_id: UUID | None = None,
    reason: str | None = None,
    time_range: IssueTimeRange | None = None,
    blocking: bool | None = None,
) -> PreflightIssue:
    return issue(
        project_id=project.id,
        check="presenter",
        code=code,
        level=level,
        message=message,
        action=action,
        fingerprint=fingerprint,
        location=IssueLocation(page_id=page_id, node="presenter", relative_path=relative_path),
        blocking=blocking,
        reason=reason or code.lower(),
        time_range=time_range,
    )
