from __future__ import annotations

from pathlib import Path

from workbench.domain.issues import IssueLevel, IssueLocation, PreflightIssue
from workbench.domain.models import ProjectManifest

from .common import digest, issue


def fingerprint(project: ProjectManifest, root: Path) -> str:
    return digest(
        {
            "pages": [
                {
                    "id": str(page.id),
                    "title": page.title,
                    "narration": page.narration.model_dump(mode="json") if page.narration else None,
                }
                for page in project.pages
            ],
            "extractions": [
                {
                    "order": item.order,
                    "needs_confirmation": item.needs_confirmation,
                    "confidence": [span.confidence for span in item.spans],
                }
                for item in project.page_extractions
            ],
            "root": str(root),
        }
    )


def check_content(project: ProjectManifest, root: Path) -> tuple[str, list[PreflightIssue]]:
    check_fingerprint = fingerprint(project, root)
    issues: list[PreflightIssue] = []
    extractions = {item.order: item for item in project.page_extractions}
    for page in project.pages:
        narration = page.narration
        if narration is None:
            issues.append(
                issue(
                    project_id=project.id,
                    check="content",
                    code="narration_missing",
                    level=IssueLevel.BLOCKING,
                    message=f"第{page.order}页尚无旁白",
                    action="生成或填写本页旁白后再确认",
                    fingerprint=check_fingerprint,
                    location=IssueLocation(page_id=page.id, node="narration"),
                )
            )
        elif narration.confirmed_revision_id != narration.revision_id:
            issues.append(
                issue(
                    project_id=project.id,
                    check="content",
                    code="narration_unconfirmed",
                    level=IssueLevel.BLOCKING,
                    message=f"第{page.order}页当前旁白版本尚未确认",
                    action="检查并确认当前旁白版本",
                    fingerprint=check_fingerprint,
                    location=IssueLocation(page_id=page.id, node="narration"),
                )
            )
        if narration is not None and narration.insufficiencies:
            issues.append(
                issue(
                    project_id=project.id,
                    check="content",
                    code="material_insufficiency",
                    level=IssueLevel.CONFIRMATION,
                    message=f"第{page.order}页存在材料不足提示",
                    action="确认材料边界或补充本页内容后继续",
                    fingerprint=check_fingerprint,
                    location=IssueLocation(page_id=page.id, node="narration"),
                    blocking=False,
                )
            )
        extraction = extractions.get(page.order)
        if extraction is not None and (
            extraction.needs_confirmation
            or any(
                span.needs_confirmation or (span.confidence is not None and span.confidence < 0.6)
                for span in extraction.spans
            )
        ):
            issues.append(
                issue(
                    project_id=project.id,
                    check="content",
                    code="ocr_needs_confirmation",
                    level=IssueLevel.CONFIRMATION,
                    message=f"第{page.order}页存在低置信度文字或 OCR 待校对区域",
                    action="定位并人工校对低置信度文字",
                    fingerprint=check_fingerprint,
                    location=IssueLocation(page_id=page.id, node="ocr"),
                    blocking=False,
                )
            )
    return check_fingerprint, issues
