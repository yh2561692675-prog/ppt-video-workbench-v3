from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from tests.integration.test_preflight_routes import _ready_app


def _stable_view(report: dict[str, object]) -> dict[str, object]:
    return {
        key: report[key]
        for key in (
            "project_fingerprint",
            "input_fingerprint",
            "check_fingerprints",
            "allowed",
            "cache_status",
            "is_stale",
        )
    } | {
        "issues": [
            {
                key: issue[key]
                for key in ("issue_id", "check", "code", "fingerprint", "blocking")
            }
            for issue in report["issues"]  # type: ignore[index]
        ]
    }


def test_fresh_preflight_is_stable_and_never_reuses_previous_result(tmp_path: Path) -> None:
    app, project = _ready_app(tmp_path, ocr_confirmation=False)

    with TestClient(app) as client:
        reports = [
            client.post(
                f"/api/projects/{project.id}/preflight", json={"fresh": True}
            ).json()["data"]
            for _ in range(3)
        ]

    assert all(report["fresh"] is True for report in reports)
    assert all(report["reused_checks"] == [] for report in reports)
    assert all(len(report["executed_checks"]) == 7 for report in reports)
    assert [_stable_view(report) for report in reports] == [_stable_view(reports[0])] * 3


def test_input_change_marks_persisted_report_stale_and_render_refreshes_it(tmp_path: Path) -> None:
    app, project = _ready_app(tmp_path, ocr_confirmation=False)

    with TestClient(app) as client:
        first = client.post(
            f"/api/projects/{project.id}/preflight", json={"fresh": True}
        ).json()["data"]
        changed = app.state.project_service.get(project.id)
        changed.pages[0].title = "changed after preflight"
        app.state.project_service.save(changed)
        stale = client.get(f"/api/projects/{project.id}/preflight").json()["data"]

    assert first["is_stale"] is False
    assert stale["is_stale"] is True
    assert stale["cache_status"] == "stale"
    assert stale["project_fingerprint"] == first["project_fingerprint"]
