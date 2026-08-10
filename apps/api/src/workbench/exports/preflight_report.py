from __future__ import annotations

from collections.abc import Iterable

from workbench.domain.issues import IssueConfirmation, IssueLevel, PreflightReport


def report_markdown(
    report: PreflightReport,
    confirmations: Iterable[IssueConfirmation] = (),
) -> str:
    notes = {item.issue_id: item.note for item in confirmations if item.report_id == report.id}
    lines = [
        "# 项目预检报告",
        "",
        f"- 报告 ID：`{report.id}`",
        f"- 检查时间：{report.checked_at.isoformat()}",
        f"- 最终结论：{'允许渲染' if report.allowed else '禁止渲染'}",
        f"- 输入指纹：`{report.input_fingerprint}`",
        "",
        "## 检查结果",
        "",
        "| 级别 | Code | 定位 | 结果 | 修复动作 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for issue in report.issues:
        location = issue.location.relative_path or issue.location.node or "项目级"
        if issue.location.page_id is not None:
            location = f"页面 {issue.location.page_id} / {location}"
        if issue.level is IssueLevel.BLOCKING:
            result = "阻断"
        elif issue.confirmed:
            result = f"已确认（{issue.confirmed_by or '未记录'}）"
        else:
            result = "待处理"
        note = notes.get(issue.issue_id)
        if note:
            result = f"{result}：{note}"
        lines.append(
            f"| {issue.level.value} | `{issue.code}` | {location} | "
            f"{issue.message} / {result} | {issue.action} |"
        )
    if not report.issues:
        lines.append("| info | `no_issue` | 项目级 | 未发现问题 | 可进入下一步 |")
    lines.extend(["", "## 执行记录", "", f"- 复用检查：{', '.join(report.reused_checks) or '无'}"])
    lines.append(f"- 重新执行检查：{', '.join(report.executed_checks) or '无'}")
    return "\n".join(lines) + "\n"
