from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from workbench.performance.budget import (
    CandidateBindingV1,
    PerformanceBudgetV1,
    approve_budget,
    baseline_evidence_from_sampler,
    propose_budget,
    write_budget,
)


def write_sampler_evidence(root: Path, *, finished: bool = True) -> tuple[Path, Path]:
    events = root / "sample.jsonl"
    summary = root / "sample-summary.json"
    start = datetime(2026, 8, 12, tzinfo=UTC)
    finished_at = start + timedelta(seconds=3)
    rows = [
        {
            "type": "session_started",
            "timestamp": start.isoformat().replace("+00:00", "Z"),
            "host": {
                "platform": "Windows-test",
                "python": "3.12",
                "cpu_count": 8,
                "gpu_probe": "not_available",
                "gpu_memory_bytes": None,
            },
        },
        {
            "type": "stage",
            "timestamp": start.isoformat().replace("+00:00", "Z"),
            "stage": "import",
            "event": "started",
        },
        {
            "type": "stage",
            "timestamp": (start + timedelta(seconds=2)).isoformat().replace("+00:00", "Z"),
            "stage": "import",
            "event": "finished",
        },
    ]
    if finished:
        rows.append(
            {
                "type": "session_finished",
                "timestamp": finished_at.isoformat().replace("+00:00", "Z"),
            }
        )
    events.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    summary.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "session_id": "sampler-test",
                "finished_at": finished_at.isoformat().replace("+00:00", "Z"),
                "events_path": events.name,
                "component_peaks": {
                    "api": {
                        "rss_bytes": 100,
                        "cpu_percent": 50.0,
                        "handle_count": 2,
                        "thread_count": 3,
                        "read_bytes": 4,
                        "write_bytes": 5,
                        "gpu_memory_bytes": None,
                    }
                },
                "temporary_space_peaks": {
                    "max_used_bytes": 6,
                    "max_file_bytes": 7,
                    "max_file_count": 8,
                    "min_free_bytes": 9,
                },
            }
        ),
        encoding="utf-8",
    )
    return summary, events


def candidate() -> CandidateBindingV1:
    return CandidateBindingV1(
        candidate_id="v1-rc-abc123-20260812T000000Z",
        source_commit="a" * 40,
        manifest_sha256="b" * 64,
    )


def test_proposed_budget_binds_evidence_and_marks_missing_phases(tmp_path: Path) -> None:
    summary, events = write_sampler_evidence(tmp_path)

    budget = propose_budget(
        candidate=candidate(),
        fixture_id="S8",
        fixture_sha256="c" * 64,
        cache_mode="cold",
        concurrency=1,
        summary_path=summary,
        events_path=events,
    )

    assert budget.status == "proposed"
    assert budget.review.reviewer is None
    assert budget.baseline.phase_metrics["import"].duration_ms == 2_000
    assert budget.baseline.phase_metrics["mux"].status == "not_observed"
    assert budget.host_profile.gpu_memory_bytes is None


def test_budget_requires_completed_sampler_and_approval_is_separate(tmp_path: Path) -> None:
    summary, incomplete_events = write_sampler_evidence(tmp_path, finished=False)
    with pytest.raises(ValueError, match="session_finished"):
        baseline_evidence_from_sampler(summary, incomplete_events)

    summary, events = write_sampler_evidence(tmp_path)
    budget = propose_budget(
        candidate=candidate(),
        fixture_id="S8",
        fixture_sha256="c" * 64,
        cache_mode="warm",
        concurrency=2,
        summary_path=summary,
        events_path=events,
    )
    approved = approve_budget(budget, "engineering-owner")
    assert approved.status == "approved"
    assert approved.review.reviewer == "engineering-owner"
    with pytest.raises(ValueError, match="reviewer"):
        approve_budget(budget, " ")


def test_budget_write_is_non_overwriting_and_contract_rejects_mismatched_review(
    tmp_path: Path,
) -> None:
    summary, events = write_sampler_evidence(tmp_path)
    budget = propose_budget(
        candidate=candidate(),
        fixture_id="S8",
        fixture_sha256="c" * 64,
        cache_mode="cold",
        concurrency=1,
        summary_path=summary,
        events_path=events,
    )
    target = tmp_path / "performance-budget-v1.json"
    write_budget(target, budget)
    with pytest.raises(FileExistsError):
        write_budget(target, budget)
    invalid = budget.model_dump()
    invalid["status"] = "approved"
    with pytest.raises(ValueError, match="must match"):
        PerformanceBudgetV1.model_validate(invalid)
