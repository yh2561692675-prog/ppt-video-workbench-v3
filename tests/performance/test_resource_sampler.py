from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

import pytest
from workbench.performance.sampler import PerformanceSampler, ProcessObservation


class SnapshotProvider:
    def __init__(self, snapshots: list[list[ProcessObservation]]) -> None:
        self.snapshots = snapshots
        self.index = 0

    def snapshot(self) -> Iterable[ProcessObservation]:
        result = self.snapshots[min(self.index, len(self.snapshots) - 1)]
        self.index += 1
        return result


def observation(
    pid: int,
    parent_pid: int | None,
    executable: str,
    start: str,
    *,
    rss: int,
    cpu: float,
) -> ProcessObservation:
    return ProcessObservation(
        pid=pid,
        parent_pid=parent_pid,
        executable=executable,
        instance_start_token=start,
        cpu_time_seconds=cpu,
        rss_bytes=rss,
        handle_count=10,
        thread_count=2,
        read_bytes=100,
        write_bytes=200,
    )


def test_sampler_records_process_tree_stage_peaks_and_pid_reuse(tmp_path: Path) -> None:
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    (temporary / "frame.png").write_bytes(b"image")
    provider = SnapshotProvider(
        [
            [
                observation(10, None, "launcher.exe", "root", rss=100, cpu=1.0),
                observation(20, 10, "python.exe", "api", rss=200, cpu=2.0),
                observation(30, 20, "ffmpeg.exe", "first", rss=300, cpu=3.0),
            ],
            [
                observation(10, None, "launcher.exe", "root", rss=120, cpu=1.2),
                observation(20, 10, "python.exe", "api", rss=250, cpu=2.2),
                observation(30, 20, "ffmpeg.exe", "reused", rss=400, cpu=4.0),
            ],
        ]
    )
    sampler = PerformanceSampler(
        tmp_path / "evidence",
        {"launcher": 10},
        temporary_root=temporary,
        provider=provider,
        session_id="sample",
    )

    sampler.start()
    sampler.record_stage("render", "started")
    sampler.sample_once()
    sampler.record_stage("render", "finished")
    summary_path = sampler.stop()

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["sample_count"] >= 3
    assert set(summary["process_instances"]) >= {
        "10:root",
        "20:api",
        "30:first",
        "30:reused",
    }
    assert summary["component_peaks"]["ffmpeg"]["rss_bytes"] == 400
    assert summary["temporary_space_peaks"]["max_file_bytes"] == 5
    assert summary["stage_events"][0]["stage"] == "render"

    events = [
        json.loads(line)
        for line in sampler.events_path.read_text(encoding="utf-8").splitlines()
    ]
    assert events[0]["type"] == "session_started"
    assert any(
        event["type"] == "process_observed" and event["instance_key"] == "30:reused"
        for event in events
    )


def test_sampler_rejects_out_of_policy_intervals_and_duplicate_output(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="between 1 and 5"):
        PerformanceSampler(
            tmp_path,
            {"api": 1},
            temporary_root=tmp_path,
            interval_seconds=0.5,
        )

    provider = SnapshotProvider([[observation(1, None, "python", "one", rss=1, cpu=0.0)]])
    first = PerformanceSampler(
        tmp_path,
        {"api": 1},
        temporary_root=tmp_path,
        provider=provider,
        session_id="same",
    )
    first.start()
    first.stop()
    second = PerformanceSampler(
        tmp_path,
        {"api": 1},
        temporary_root=tmp_path,
        provider=provider,
        session_id="same",
    )
    with pytest.raises(FileExistsError):
        second.start()


def test_sampler_records_missing_named_root_without_forging_a_process(tmp_path: Path) -> None:
    provider = SnapshotProvider([[observation(10, None, "python", "one", rss=1, cpu=0.0)]])
    sampler = PerformanceSampler(
        tmp_path,
        {"api": 10, "worker": 99},
        temporary_root=tmp_path,
        provider=provider,
        session_id="missing-root",
    )

    sampler.start()
    summary = json.loads(sampler.stop().read_text(encoding="utf-8"))

    assert summary["roots_not_observed"] == {"worker": 99}


def test_sampler_recreates_owned_evidence_directory_before_append(tmp_path: Path) -> None:
    provider = SnapshotProvider(
        [[observation(10, None, "python", "one", rss=1, cpu=0.0)]]
    )
    evidence = tmp_path / "evidence"
    sampler = PerformanceSampler(
        evidence,
        {"api": 10},
        temporary_root=tmp_path,
        provider=provider,
        session_id="recreate-dir",
    )

    sampler.start()
    import shutil

    shutil.rmtree(evidence)
    summary = json.loads(sampler.stop().read_text(encoding="utf-8"))

    assert summary["sample_count"] >= 2
    assert sampler.events_path.is_file()
