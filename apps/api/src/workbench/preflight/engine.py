from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from workbench.domain.issues import IssueLevel, IssueLocation, PreflightIssue, PreflightReport
from workbench.domain.models import ProjectManifest
from workbench.runtime.layout import RuntimeComponentMissingError, RuntimeLayout

from .checks.audio import check_audio
from .checks.common import digest
from .checks.common import issue as build_issue
from .checks.content import check_content
from .checks.materials import check_materials
from .checks.presenter import check_presenter_source
from .checks.runtime import check_runtime
from .checks.video import check_video

RuntimeProbe = Callable[[], Mapping[str, str]]


class PreflightEngine:
    def __init__(
        self,
        workspace_root: Path,
        *,
        runtime_probe: RuntimeProbe | None = None,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.runtime_probe = runtime_probe or self._default_runtime_probe

    def run_preflight(
        self,
        project: ProjectManifest,
        scope: set[str] | list[str] | None = None,
        previous: PreflightReport | None = None,
        *,
        fresh: bool = False,
    ) -> PreflightReport:
        root = (self.workspace_root / project.project_dir).resolve()
        selected = set(
            scope or {"materials", "content", "audio", "video", "presenter", "runtime", "resources"}
        )
        checkers: dict[str, Callable[[], tuple[str, list[PreflightIssue]]]] = {
            "materials": lambda: check_materials(project, root),
            "content": lambda: check_content(project, root),
            "audio": lambda: check_audio(project, root),
            "video": lambda: check_video(project, root),
            "presenter": lambda: check_presenter_source(project, root),
            "runtime": lambda: check_runtime(project, root, self.runtime_probe()),
            "resources": lambda: self._check_resources(project, root),
        }
        issues: list[PreflightIssue] = []
        check_fingerprints: dict[str, str] = {}
        reused: list[str] = []
        executed: list[str] = []
        reusable_previous = None if fresh else previous
        previous_issues = self._group_previous_issues(reusable_previous)
        for name, checker in checkers.items():
            if name not in selected:
                if reusable_previous is not None and name in reusable_previous.check_fingerprints:
                    check_fingerprints[name] = reusable_previous.check_fingerprints[name]
                    issues.extend(previous_issues.get(name, []))
                    reused.append(name)
                continue
            fingerprint, fresh_issues = checker()
            check_fingerprints[name] = fingerprint
            if (
                reusable_previous is not None
                and reusable_previous.check_fingerprints.get(name) == fingerprint
            ):
                issues.extend(previous_issues.get(name, []))
                reused.append(name)
            else:
                issues.extend(fresh_issues)
                executed.append(name)

        project_fingerprint = self.project_fingerprint(project)
        input_fingerprint = digest({"project": project_fingerprint, "checks": check_fingerprints})
        cache_status: Literal["fresh", "reused", "mixed", "stale"] = (
            "fresh"
            if fresh or not reused
            else "reused"
            if not executed
            else "mixed"
        )
        report = PreflightReport(
            project_id=project.id,
            checked_at=datetime.now(UTC),
            scope=sorted(selected),
            project_fingerprint=project_fingerprint,
            input_fingerprint=input_fingerprint,
            check_fingerprints=check_fingerprints,
            issues=issues,
            allowed=not any(
                issue.blocking
                or (
                    issue.level in {IssueLevel.CONFIRMATION, IssueLevel.REQUIRED_WARNING}
                    and not issue.confirmed
                )
                for issue in issues
            ),
            reused_checks=reused,
            executed_checks=executed,
            fresh=fresh,
            cache_status=cache_status,
        )
        snapshot_path = self._write_snapshot(root, report)
        return report.model_copy(update={"snapshot_path": snapshot_path})

    def _check_resources(
        self, project: ProjectManifest, root: Path
    ) -> tuple[str, list[PreflightIssue]]:
        free = shutil.disk_usage(root if root.exists() else self.workspace_root).free
        writable = root.is_dir() and os.access(root, os.W_OK)
        fingerprint = digest(
            {
                "disk_space_sufficient": free >= 1_048_576,
                "writable": writable,
            }
        )
        issues: list[PreflightIssue] = []
        if not writable:
            issues.append(
                self._resource_issue(
                    project,
                    "output_directory_not_writable",
                    "输出目录不可写",
                    "修复输出目录权限后重新运行预检",
                    fingerprint,
                )
            )
        if free < 1_048_576:
            issues.append(
                self._resource_issue(
                    project,
                    "disk_space_low",
                    "可用磁盘空间不足",
                    "清理可重建缓存或选择空间充足的输出目录",
                    fingerprint,
                )
            )
        return fingerprint, issues

    @staticmethod
    def project_fingerprint(project: ProjectManifest) -> str:
        """Hash user/render inputs while excluding preflight's own persistence fields."""
        payload = project.model_dump(
            mode="json",
            exclude={
                "updated_at",
                "audit_log",
                "preflight_report",
                "preflight_history",
                "issue_confirmations",
                "video_preflight",
                "video_export",
            },
        )
        return digest(payload)

    @staticmethod
    def _resource_issue(
        project: ProjectManifest,
        code: str,
        message: str,
        action: str,
        fingerprint: str,
    ) -> PreflightIssue:
        return build_issue(
            project_id=project.id,
            check="resources",
            code=code,
            level=IssueLevel.BLOCKING,
            message=message,
            action=action,
            fingerprint=fingerprint,
            location=IssueLocation(node="resources"),
        )

    @staticmethod
    def _group_previous_issues(
        previous: PreflightReport | None,
    ) -> dict[str, list[PreflightIssue]]:
        grouped: dict[str, list[PreflightIssue]] = {}
        if previous is None:
            return grouped
        for previous_issue in previous.issues:
            grouped.setdefault(previous_issue.check, []).append(previous_issue)
        return grouped

    def _write_snapshot(self, root: Path, report: PreflightReport) -> str:
        report_dir = root / "09_日志" / "预检"
        report_dir.mkdir(parents=True, exist_ok=True)
        relative_path = f"09_日志/预检/预检报告-{report.id}.json"
        target = root / relative_path
        temp = target.with_name(f".{target.name}.tmp")
        payload = report.model_copy(update={"snapshot_path": relative_path}).model_dump_json(
            indent=2
        )
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
        return relative_path

    @staticmethod
    def _default_runtime_probe() -> Mapping[str, str]:
        try:
            runtime = RuntimeLayout.from_environment().require_renderer()
        except RuntimeComponentMissingError:
            if not os.environ.get("WORKBENCH_RUNTIME_ROOT"):
                return {
                    "python": sys.version.split()[0],
                    "node": shutil.which("node") or "",
                    "ffmpeg": shutil.which("ffmpeg") or "",
                    "ffprobe": shutil.which("ffprobe") or "",
                }
            return {"python": sys.version.split()[0], "node": "", "ffmpeg": "", "ffprobe": ""}
        return {
            "python": sys.version.split()[0],
            "node": str(runtime.node_executable),
            "ffmpeg": str(runtime.ffmpeg_executable),
            "ffprobe": str(runtime.ffprobe_executable),
        }
