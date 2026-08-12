"""Versioned performance-baseline contract and fail-closed budget workflow."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_SHA256 = r"^[0-9a-f]{64}$"
_COMMIT = r"^[0-9a-f]{40}$"
_CANDIDATE = r"^v1-rc-[a-z0-9]+-\d{8}T\d{6}Z$"
_PHASES = (
    "startup_to_health",
    "import",
    "preflight",
    "preview",
    "page_render",
    "mux",
    "package",
)
PhaseName = Literal[
    "startup_to_health", "import", "preflight", "preview", "page_render", "mux", "package"
]
CacheMode = Literal["cold", "warm", "selective_invalidation"]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ArtifactReferenceV1(_FrozenModel):
    path: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: Annotated[str, Field(pattern=_SHA256)]


class CandidateBindingV1(_FrozenModel):
    candidate_id: Annotated[str, Field(pattern=_CANDIDATE)]
    source_commit: Annotated[str, Field(pattern=_COMMIT)]
    manifest_sha256: Annotated[str, Field(pattern=_SHA256)]


class HostProfileV1(_FrozenModel):
    profile_id: Annotated[str, Field(pattern=_SHA256)]
    platform: str = Field(min_length=1)
    python: str = Field(min_length=1)
    cpu_count: int | None = Field(default=None, ge=1)
    gpu_probe: str = Field(min_length=1)
    gpu_memory_bytes: int | None = Field(default=None, ge=0)


class WorkloadProfileV1(_FrozenModel):
    fixture_id: str = Field(min_length=1)
    fixture_sha256: Annotated[str, Field(pattern=_SHA256)]
    cache_mode: CacheMode
    concurrency: int = Field(ge=1)


class PhaseMeasurementV1(_FrozenModel):
    status: Literal["observed", "not_observed"]
    duration_ms: int | None = Field(default=None, ge=0)
    reason: str | None = None

    @model_validator(mode="after")
    def require_consistent_value(self) -> PhaseMeasurementV1:
        if self.status == "observed" and self.duration_ms is None:
            raise ValueError("observed phase requires duration_ms")
        if self.status == "not_observed" and (self.duration_ms is not None or not self.reason):
            raise ValueError("not_observed phase requires reason and no duration_ms")
        return self


class ComponentPeakV1(_FrozenModel):
    rss_bytes: int | None = Field(default=None, ge=0)
    cpu_percent: float | None = Field(default=None, ge=0)
    handle_count: int | None = Field(default=None, ge=0)
    thread_count: int | None = Field(default=None, ge=0)
    read_bytes: int | None = Field(default=None, ge=0)
    write_bytes: int | None = Field(default=None, ge=0)
    gpu_memory_bytes: int | None = Field(default=None, ge=0)


class TemporarySpacePeakV1(_FrozenModel):
    max_used_bytes: int | None = Field(default=None, ge=0)
    max_file_bytes: int | None = Field(default=None, ge=0)
    max_file_count: int | None = Field(default=None, ge=0)
    min_free_bytes: int | None = Field(default=None, ge=0)


class BaselineEvidenceV1(_FrozenModel):
    session_id: str = Field(min_length=1)
    captured_at: str = Field(min_length=1)
    summary: ArtifactReferenceV1
    events: ArtifactReferenceV1
    phase_metrics: dict[PhaseName, PhaseMeasurementV1]
    component_peaks: dict[str, ComponentPeakV1]
    temporary_space_peaks: TemporarySpacePeakV1

    @model_validator(mode="after")
    def require_complete_phase_catalog(self) -> BaselineEvidenceV1:
        if set(self.phase_metrics) != set(_PHASES):
            raise ValueError("phase_metrics must define every supported phase exactly once")
        _parse_timestamp(self.captured_at)
        return self


class RegressionThresholdsV1(_FrozenModel):
    max_phase_regression_percent: float = Field(default=20.0, ge=0, le=100)
    max_soak_rss_growth_percent: float = Field(default=15.0, ge=0, le=100)
    allow_oom: Literal[False] = False
    min_free_disk_bytes: int = Field(default=5 * 1024**3, ge=0)
    max_orphan_processes: int = Field(default=0, ge=0)
    max_unpublished_temporary_files: int = Field(default=0, ge=0)


class BudgetReviewV1(_FrozenModel):
    status: Literal["proposed", "approved"] = "proposed"
    reviewer: str | None = None
    reviewed_at: str | None = None

    @model_validator(mode="after")
    def require_reviewer_for_approval(self) -> BudgetReviewV1:
        if self.status == "approved":
            if not self.reviewer or not self.reviewed_at:
                raise ValueError("approved budget requires reviewer and reviewed_at")
            _parse_timestamp(self.reviewed_at)
        elif self.reviewer is not None or self.reviewed_at is not None:
            raise ValueError("proposed budget must not claim reviewer approval")
        return self


class PerformanceBudgetV1(_FrozenModel):
    schema_version: Literal["1.0"] = "1.0"
    status: Literal["proposed", "approved"] = "proposed"
    candidate: CandidateBindingV1
    host_profile: HostProfileV1
    workload: WorkloadProfileV1
    baseline: BaselineEvidenceV1
    thresholds: RegressionThresholdsV1 = RegressionThresholdsV1()
    review: BudgetReviewV1 = BudgetReviewV1()

    @model_validator(mode="after")
    def require_matching_review_state(self) -> PerformanceBudgetV1:
        if self.status != self.review.status:
            raise ValueError("budget status must match review status")
        return self


def artifact_reference(path: Path) -> ArtifactReferenceV1:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError(f"evidence artifact is missing: {resolved}")
    return ArtifactReferenceV1(
        path=str(resolved), size_bytes=resolved.stat().st_size, sha256=_sha256(resolved)
    )


def read_jsonl(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"cannot read JSONL evidence: {path}") from error
    for index, line in enumerate(content.splitlines(), start=1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSONL event at line {index}") from error
        if not isinstance(value, dict):
            raise ValueError(f"JSONL event at line {index} must be an object")
        rows.append(value)
    if not rows:
        raise ValueError("JSONL evidence must not be empty")
    return rows


def _host_profile(session_started: Mapping[str, object]) -> HostProfileV1:
    host = session_started.get("host")
    if not isinstance(host, dict):
        raise ValueError("session_started.host is missing")
    platform = host.get("platform")
    python = host.get("python")
    gpu_probe = host.get("gpu_probe")
    cpu_count = host.get("cpu_count")
    gpu_memory = host.get("gpu_memory_bytes")
    if not (
        isinstance(platform, str) and isinstance(python, str) and isinstance(gpu_probe, str)
    ):
        raise ValueError("session host profile is incomplete")
    if cpu_count is not None and (not isinstance(cpu_count, int) or cpu_count < 1):
        raise ValueError("session host cpu_count is invalid")
    if gpu_memory is not None and (not isinstance(gpu_memory, int) or gpu_memory < 0):
        raise ValueError("session host gpu_memory_bytes is invalid")
    canonical = json.dumps(host, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return HostProfileV1(
        profile_id=hashlib.sha256(canonical).hexdigest(),
        platform=platform,
        python=python,
        cpu_count=cpu_count,
        gpu_probe=gpu_probe,
        gpu_memory_bytes=gpu_memory,
    )


def _phase_metrics(events: Iterable[Mapping[str, object]]) -> dict[PhaseName, PhaseMeasurementV1]:
    starts: dict[str, datetime] = {}
    durations: dict[str, int] = {}
    for event in events:
        if event.get("type") != "stage":
            continue
        stage = event.get("stage")
        state = event.get("event")
        timestamp = event.get("timestamp")
        if not (
            isinstance(stage, str) and isinstance(state, str) and isinstance(timestamp, str)
        ):
            raise ValueError("stage event is incomplete")
        if stage not in _PHASES:
            continue
        if state == "started":
            starts[stage] = _parse_timestamp(timestamp)
        elif state == "finished" and stage in starts:
            elapsed = _parse_timestamp(timestamp) - starts.pop(stage)
            durations[stage] = max(0, round(elapsed.total_seconds() * 1000))
    result: dict[PhaseName, PhaseMeasurementV1] = {}
    for phase in _PHASES:
        typed_phase: PhaseName = phase  # type: ignore[assignment]
        if phase in durations:
            result[typed_phase] = PhaseMeasurementV1(
                status="observed", duration_ms=durations[phase]
            )
        else:
            reason = "stage did not finish" if phase in starts else "stage was not recorded"
            result[typed_phase] = PhaseMeasurementV1(status="not_observed", reason=reason)
    return result


def _component_peaks(value: object) -> dict[str, ComponentPeakV1]:
    if not isinstance(value, dict):
        raise ValueError("summary.component_peaks is missing")
    result: dict[str, ComponentPeakV1] = {}
    for role, raw in value.items():
        if not isinstance(role, str) or not isinstance(raw, dict):
            raise ValueError("summary.component_peaks is invalid")
        result[role] = ComponentPeakV1.model_validate(raw)
    return result


def baseline_evidence_from_sampler(
    summary_path: Path, events_path: Path
) -> tuple[HostProfileV1, BaselineEvidenceV1]:
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read sampler summary: {summary_path}") from error
    if not isinstance(summary, dict) or summary.get("schema_version") != "1.0":
        raise ValueError("sampler summary schema_version must be 1.0")
    events = read_jsonl(events_path)
    session_started = events[0]
    if session_started.get("type") != "session_started":
        raise ValueError("first sampler event must be session_started")
    if events[-1].get("type") != "session_finished":
        raise ValueError("last sampler event must be session_finished")
    session_id = summary.get("session_id")
    captured_at = summary.get("finished_at")
    temporary = summary.get("temporary_space_peaks")
    if not (
        isinstance(session_id, str) and isinstance(captured_at, str) and isinstance(temporary, dict)
    ):
        raise ValueError("sampler summary is incomplete")
    expected_events_name = summary.get("events_path")
    if expected_events_name != events_path.name:
        raise ValueError("sampler summary does not bind the supplied JSONL evidence")
    return (
        _host_profile(session_started),
        BaselineEvidenceV1(
            session_id=session_id,
            captured_at=captured_at,
            summary=artifact_reference(summary_path),
            events=artifact_reference(events_path),
            phase_metrics=_phase_metrics(events),
            component_peaks=_component_peaks(summary.get("component_peaks")),
            temporary_space_peaks=TemporarySpacePeakV1.model_validate(temporary),
        ),
    )


def propose_budget(
    *,
    candidate: CandidateBindingV1,
    fixture_id: str,
    fixture_sha256: str,
    cache_mode: CacheMode,
    concurrency: int,
    summary_path: Path,
    events_path: Path,
) -> PerformanceBudgetV1:
    host_profile, baseline = baseline_evidence_from_sampler(summary_path, events_path)
    return PerformanceBudgetV1(
        candidate=candidate,
        host_profile=host_profile,
        workload=WorkloadProfileV1(
            fixture_id=fixture_id,
            fixture_sha256=fixture_sha256,
            cache_mode=cache_mode,
            concurrency=concurrency,
        ),
        baseline=baseline,
    )


def approve_budget(budget: PerformanceBudgetV1, reviewer: str) -> PerformanceBudgetV1:
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("reviewer must not be empty")
    return budget.model_copy(
        update={
            "status": "approved",
            "review": BudgetReviewV1(status="approved", reviewer=reviewer, reviewed_at=_utc_now()),
        }
    )


def write_budget(path: Path, budget: PerformanceBudgetV1) -> Path:
    """Publish an immutable proposed or approved budget without replacement."""

    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(budget.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        )
    return target
