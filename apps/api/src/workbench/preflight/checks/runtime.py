from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from workbench.domain.issues import IssueLevel, IssueLocation, PreflightIssue
from workbench.domain.models import ProjectManifest

from .common import digest, issue


def fingerprint(project: ProjectManifest, root: Path, probe: Mapping[str, str]) -> str:
    return digest(
        {"probe": dict(sorted(probe.items())), "root": str(root), "project": str(project.id)}
    )


def check_runtime(
    project: ProjectManifest, root: Path, probe: Mapping[str, str]
) -> tuple[str, list[PreflightIssue]]:
    check_fingerprint = fingerprint(project, root, probe)
    if not probe:
        return check_fingerprint, [
            issue(
                project_id=project.id,
                check="runtime",
                code="runtime_probe_unavailable",
                level=IssueLevel.BLOCKING,
                message="本地运行环境检测未返回结果",
                action="重新运行 scripts/prepare-runtime.ps1 并重建安装包，然后再运行环境诊断",
                fingerprint=check_fingerprint,
                location=IssueLocation(node="runtime"),
            )
        ]
    issues: list[PreflightIssue] = []
    for component in ("python", "node", "ffmpeg", "ffprobe"):
        if not probe.get(component):
            issues.append(
                issue(
                    project_id=project.id,
                    check="runtime",
                    code="runtime_component_missing",
                    level=IssueLevel.BLOCKING,
                    message=f"运行组件 {component} 不可用",
                    action="重新运行 scripts/prepare-runtime.ps1 并重建安装包，然后再运行环境诊断",
                    fingerprint=check_fingerprint,
                    location=IssueLocation(node="runtime", relative_path=component),
                )
            )
    return check_fingerprint, issues
