from __future__ import annotations

from pathlib import Path

from workbench.domain.issues import IssueLevel, IssueLocation, PreflightIssue
from workbench.domain.models import ProjectManifest

from .common import digest, issue, relative


def _resolved_preview_path(root: Path, preview: Path | str | None) -> Path | None:
    if preview is None:
        return None
    stored_path = Path(preview)
    return (stored_path if stored_path.is_absolute() else root / stored_path).resolve()


def _preview_file_state(root: Path, preview: Path | str | None) -> dict[str, object]:
    resolved = _resolved_preview_path(root, preview)
    if resolved is None:
        return {"path": None, "is_file": False, "size": None, "mtime_ns": None}
    try:
        status = resolved.stat()
        is_file = resolved.is_file()
    except OSError:
        return {
            "path": str(resolved),
            "is_file": False,
            "size": None,
            "mtime_ns": None,
        }
    return {
        "path": str(resolved),
        "is_file": is_file,
        "size": status.st_size if is_file else None,
        "mtime_ns": status.st_mtime_ns if is_file else None,
    }


def fingerprint(project: ProjectManifest, root: Path) -> str:
    payload = {
        "sources": [item.model_dump(mode="json") for item in project.source_files],
        "pages": [
            {
                "id": str(page.id),
                "order": page.order,
                "source_file_id": str(page.source_file_id),
            }
            for page in project.pages
        ],
        "extractions": [
            {
                "id": str(item.id),
                "order": item.order,
                "preview": str(item.preview_path),
                "preview_file": _preview_file_state(root, item.preview_path),
                "width": item.width,
                "height": item.height,
            }
            for item in project.page_extractions
        ],
        "root": str(root),
    }
    return digest(payload)


def check_materials(project: ProjectManifest, root: Path) -> tuple[str, list[PreflightIssue]]:
    check_fingerprint = fingerprint(project, root)
    issues: list[PreflightIssue] = []
    if not project.pages:
        issues.append(
            issue(
                project_id=project.id,
                check="materials",
                code="pages_missing",
                level=IssueLevel.BLOCKING,
                message="项目尚未识别出任何页面",
                action="重新导入并解析课件",
                fingerprint=check_fingerprint,
            )
        )
        return check_fingerprint, issues

    orders = sorted(page.order for page in project.pages)
    if orders != list(range(1, len(orders) + 1)):
        issues.append(
            issue(
                project_id=project.id,
                check="materials",
                code="page_order_invalid",
                level=IssueLevel.BLOCKING,
                message="页面序号不连续或存在重复",
                action="在材料解析步骤修正页面顺序",
                fingerprint=check_fingerprint,
            )
        )

    extractions = {item.order: item for item in project.page_extractions}
    for page in project.pages:
        extraction = extractions.get(page.order)
        preview = extraction.preview_path if extraction is not None else None
        preview_path = _resolved_preview_path(root, preview)
        if preview_path is None or not preview_path.is_file():
            relative_path = (
                relative(root, preview_path)
                if preview_path is not None
                else f"02_页面预览/page-{page.order:04d}.png"
            )
            issues.append(
                issue(
                    project_id=project.id,
                    check="materials",
                    code="page_preview_missing",
                    level=IssueLevel.BLOCKING,
                    message=f"第{page.order}页预览图不存在",
                    action="重新生成页面预览并再次运行预检",
                    fingerprint=check_fingerprint,
                    location=IssueLocation(
                        page_id=page.id,
                        node="materials",
                        relative_path=relative_path,
                    ),
                )
            )
        elif extraction is not None and (
            extraction.width is not None
            and extraction.height is not None
            and (extraction.width < 640 or extraction.height < 360)
        ):
            issues.append(
                issue(
                    project_id=project.id,
                    check="materials",
                    code="page_resolution_low",
                    level=IssueLevel.REQUIRED_WARNING,
                    message=f"第{page.order}页预览分辨率偏低",
                    action="确认画面清晰度，必要时重新生成高清预览",
                    fingerprint=check_fingerprint,
                    location=IssueLocation(page_id=page.id, node="materials"),
                    blocking=False,
                )
            )

    for source in project.source_files:
        if not (root / source.copied_path).is_file():
            issues.append(
                issue(
                    project_id=project.id,
                    check="materials",
                    code="source_missing",
                    level=IssueLevel.BLOCKING,
                    message=f"源文件 {source.original_name} 不存在",
                    action="恢复项目内源文件或重新导入材料",
                    fingerprint=check_fingerprint,
                    location=IssueLocation(node="materials", relative_path=source.copied_path),
                )
            )
    return check_fingerprint, issues
