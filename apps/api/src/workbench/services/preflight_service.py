from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from workbench.domain.issues import (
    IssueConfirmation,
    IssueLevel,
    PreflightIssue,
    PreflightReport,
)
from workbench.domain.models import AuditEvent, ProjectManifest
from workbench.services.project_service import ProjectService
from workbench.video.preview_service import VideoPreviewService

from ..preflight.engine import PreflightEngine


class PreflightError(RuntimeError):
    def __init__(self, code: str, message: str, action: str) -> None:
        super().__init__(message)
        self.code = code
        self.action = action


class PreflightService:
    def __init__(
        self,
        projects: ProjectService,
        engine: PreflightEngine,
        video_preview: VideoPreviewService,
    ) -> None:
        self.projects = projects
        self.engine = engine
        self.video_preview = video_preview

    def run(self, project_id: UUID, scope: Iterable[str] | None = None) -> PreflightReport:
        project = self.projects.get(project_id)
        report = self.engine.run_preflight(
            project,
            scope=set(scope) if scope is not None else None,
            previous=project.preflight_report,
        )
        report = self._apply_existing_confirmations(project, report)
        return self._persist_report(project, report, action="preflight_completed")

    def get(self, project_id: UUID) -> PreflightReport:
        project = self.projects.get(project_id)
        if project.preflight_report is None:
            return self.run(project_id)
        return project.preflight_report

    def confirm(
        self,
        project_id: UUID,
        issue_id: UUID,
        *,
        actor: str,
        note: str,
    ) -> PreflightReport:
        project = self.projects.get(project_id)
        report = project.preflight_report
        if report is None:
            raise PreflightError(
                "preflight_missing",
                "尚未生成当前项目的预检报告",
                "先运行完整预检后再确认问题",
            )
        try:
            target = next(issue for issue in report.issues if issue.issue_id == issue_id)
        except StopIteration as error:
            raise PreflightError(
                "issue_not_found",
                "预检问题不存在或已因输入变化失效",
                "刷新预检报告后重新选择问题",
            ) from error
        if target.level is IssueLevel.BLOCKING or target.blocking:
            raise PreflightError(
                "blocking_issue_not_confirmable",
                "阻断错误不能通过人工确认绕过",
                target.action,
            )
        clean_actor = actor.strip()
        clean_note = note.strip()
        if not clean_actor or not clean_note:
            raise PreflightError(
                "confirmation_required",
                "确认人和确认说明不能为空",
                "填写确认人及处理说明后重试",
            )
        now = datetime.now(UTC)
        confirmation = IssueConfirmation(
            issue_id=issue_id,
            report_id=report.id,
            actor=clean_actor,
            note=clean_note,
            confirmed_at=now,
        )
        updated_issues = [
            item.model_copy(
                update={
                    "confirmed": True,
                    "confirmed_by": clean_actor,
                    "confirmed_at": now,
                }
            )
            if item.issue_id == issue_id
            else item
            for item in report.issues
        ]
        updated_report = report.model_copy(
            update={
                "issues": updated_issues,
                "allowed": _report_allowed(updated_issues),
            }
        )
        latest_confirmations = [
            item for item in project.issue_confirmations if item.issue_id != issue_id
        ]
        latest_confirmations.append(confirmation)
        updated_project = project.model_copy(
            update={
                "preflight_report": updated_report,
                "issue_confirmations": latest_confirmations,
                "audit_log": [
                    *project.audit_log,
                    AuditEvent(
                        action="preflight_issue_confirmed",
                        occurred_at=now,
                        details={
                            "issue_id": str(issue_id),
                            "report_id": str(report.id),
                            "actor": clean_actor,
                        },
                    ),
                ],
            }
        )
        self.projects.save(updated_project)
        self._rewrite_snapshot(updated_project.project_dir, updated_report)
        return updated_report

    def render_gate(self, project_id: UUID) -> PreflightReport:
        self.video_preview.preflight(project_id)
        latest = self.projects.get(project_id)
        report = self.engine.run_preflight(
            latest,
            previous=latest.preflight_report,
        )
        report = self._apply_existing_confirmations(latest, report)
        return self._persist_report(latest, report, action="preflight_render_gate")

    def can_enter_render(self, project: ProjectManifest) -> bool:
        return self.render_gate(project.id).allowed

    def _persist_report(
        self,
        project: ProjectManifest,
        report: PreflightReport,
        *,
        action: str,
    ) -> PreflightReport:
        now = datetime.now(UTC)
        project_dir = project.project_dir
        audit_log = list(project.audit_log)
        audit_log.append(
            AuditEvent(
                action=action,
                occurred_at=now,
                details={
                    "report_id": str(report.id),
                    "allowed": report.allowed,
                    "issue_count": len(report.issues),
                },
            )
        )
        history = list(project.preflight_history)
        if report.snapshot_path is not None:
            history.append(report.snapshot_path)
        updated = project.model_copy(
            update={
                "preflight_report": report,
                "preflight_history": history,
                "audit_log": audit_log,
            }
        )
        saved = self.projects.save(updated)
        self._rewrite_snapshot(project_dir, report)
        return saved.preflight_report or report

    def _apply_existing_confirmations(
        self, project: ProjectManifest, report: PreflightReport
    ) -> PreflightReport:
        confirmations = {item.issue_id: item for item in project.issue_confirmations}
        updated: list[PreflightIssue] = []
        for issue in report.issues:
            confirmation = confirmations.get(issue.issue_id)
            if confirmation is None or (
                project.preflight_report is not None
                and confirmation.report_id != project.preflight_report.id
            ):
                updated.append(issue)
                continue
            updated.append(
                issue.model_copy(
                    update={
                        "confirmed": True,
                        "confirmed_by": confirmation.actor,
                        "confirmed_at": confirmation.confirmed_at,
                    }
                )
            )
        return report.model_copy(update={"issues": updated, "allowed": _report_allowed(updated)})

    def _rewrite_snapshot(self, project_dir: str, report: PreflightReport) -> None:
        if report.snapshot_path is None:
            return
        root = (self.projects.workspace_root / project_dir).resolve()
        target = (root / report.snapshot_path).resolve()
        if root not in target.parents:
            raise PreflightError(
                "preflight_snapshot_path_invalid",
                "预检报告路径超出项目目录",
                "请检查项目目录后重试",
            )
        temp = target.with_name(f".{target.name}.tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(report.model_dump_json(indent=2))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)


def _report_allowed(issues: list[PreflightIssue]) -> bool:
    return not any(
        issue.blocking
        or (
            issue.level in {IssueLevel.CONFIRMATION, IssueLevel.REQUIRED_WARNING}
            and not issue.confirmed
        )
        for issue in issues
    )
