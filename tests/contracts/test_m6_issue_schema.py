from __future__ import annotations

from workbench.domain.issues import IssueLevel, IssueLocation, PreflightIssue, PreflightReport


def test_m6_issue_contract_forbids_unstructured_fields() -> None:
    issue = PreflightIssue(
        code="page_preview_missing",
        level=IssueLevel.BLOCKING,
        message="页面预览缺失",
        action="重新生成页面预览",
        location=IssueLocation(node="materials", relative_path="02_页面预览/page-0001.png"),
        fingerprint="a" * 64,
    )

    assert issue.blocking is True
    assert issue.location.node == "materials"
    try:
        PreflightReport.model_validate({"unknown": True})
    except ValueError as error:
        assert "unknown" in str(error)
    else:
        raise AssertionError("PreflightReport must reject unknown fields")
