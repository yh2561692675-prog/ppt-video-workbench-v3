"""Deterministic S8 page-cache acceptance evidence.

This module intentionally exercises the existing ``VideoRenderService`` page
cache in an isolated, newly-created project directory.  It does not delete a
user cache or claim to measure the complete production export pipeline; the
result is specifically evidence for the cold/warm/selective page-cache
contract required by DP42.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from PIL import Image

from workbench.video.models import ProjectVideoProps, VideoPageProps
from workbench.video.render_service import PillowPageRenderer, RenderedPage, VideoRenderService

_SCHEMA_VERSION = "1.0"
_SELECTIVE_PAGE_ORDER = 4


@dataclass(frozen=True, slots=True)
class PageCacheArtifact:
    page_order: int
    cached: bool
    cache_key: str
    artifact_sha256: str
    artifact_size_bytes: int


@dataclass(frozen=True, slots=True)
class CachePhaseEvidence:
    name: str
    duration_ms: int
    cache_hits: int
    cache_misses: int
    page_graph_hash: str
    artifacts: tuple[PageCacheArtifact, ...]


@dataclass(frozen=True, slots=True)
class CacheCycleEvidence:
    cold: CachePhaseEvidence
    warm: CachePhaseEvidence
    selective_invalidation: CachePhaseEvidence
    changed_page_order: int
    source_before_sha256: str
    source_after_sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def execute_s8_cache_cycle(project_root: Path, *, page_count: int = 8) -> CacheCycleEvidence:
    """Run cold, warm and one-page-invalidated page-cache cycles in ``project_root``."""

    if page_count != 8:
        raise ValueError("DP42 accepts only the S8 eight-page fixture")
    project_root = project_root.resolve()
    if project_root.exists():
        raise FileExistsError(f"cache acceptance project root already exists: {project_root}")
    project_root.mkdir(parents=True)
    props = _create_props(project_root, page_count)
    service = VideoRenderService(project_root, PillowPageRenderer())

    cold = _run_phase("cold", service, props)
    warm = _run_phase("warm", service, props)

    source = project_root / props.pages[_SELECTIVE_PAGE_ORDER - 1].image_path
    source_before = sha256_file(source)
    _write_page_image(source, _SELECTIVE_PAGE_ORDER, variant=1)
    source_after = sha256_file(source)
    if source_before == source_after:
        raise RuntimeError("selective invalidation source did not change")
    selective = _run_phase("selective_invalidation", service, props)
    result = CacheCycleEvidence(
        cold=cold,
        warm=warm,
        selective_invalidation=selective,
        changed_page_order=_SELECTIVE_PAGE_ORDER,
        source_before_sha256=source_before,
        source_after_sha256=source_after,
    )
    _validate_cycle(result, page_count)
    return result


def run_cache_acceptance(
    *,
    repo_root: Path,
    candidate: dict[str, object],
    candidate_manifest_path: Path,
    output_root: Path,
    fixture_contract: Path,
) -> Path:
    """Publish one non-overwriteable S8 cache evidence document.

    Candidate validation is deliberately handled by the CLI before this
    function.  The output root is restricted to the repository's ignored
    ``test-results`` tree so the harness cannot clean or repurpose a caller's
    arbitrary cache directory.
    """

    repo_root = repo_root.resolve()
    output_root = output_root.resolve()
    allowed_root = (repo_root / "test-results").resolve()
    try:
        output_root.relative_to(allowed_root)
    except ValueError as error:
        raise ValueError("output_root must remain inside repository test-results") from error
    fixture_contract = fixture_contract.resolve()
    fixture = _load_s8_fixture(fixture_contract)
    candidate_id = candidate.get("candidate_id")
    source = candidate.get("source")
    if not isinstance(candidate_id, str) or not isinstance(source, dict):
        raise ValueError("validated candidate manifest is incomplete")
    source_commit = source.get("commit")
    if not isinstance(source_commit, str):
        raise ValueError("validated candidate source commit is missing")

    run_id = f"cache-s8-{time.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
    run_root = output_root / candidate_id / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    cycle = execute_s8_cache_cycle(run_root / "project", page_count=fixture["page_count"])
    evidence_path = run_root / "cache-acceptance-v1.json"
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "status": "passed",
        "run_id": run_id,
        "candidate": {
            "candidate_id": candidate_id,
            "source_commit": source_commit,
            "manifest_sha256": sha256_file(candidate_manifest_path),
        },
        "fixture": {
            "id": "DG2-S8-synthetic-v1",
            "contract_path": str(fixture_contract),
            "contract_sha256": sha256_file(fixture_contract),
            "page_count": fixture["page_count"],
        },
        "renderer": {
            "id": "pillow-page-renderer",
            "artifact_format": "png-bytes-in-page-cache-artifact",
            "scope": "VideoRenderService page cache only; not final MP4/package acceptance",
        },
        "project_root": str((run_root / "project").resolve()),
        "cycle": _cycle_payload(cycle),
    }
    _write_new_json(evidence_path, payload)
    return evidence_path


def _load_s8_fixture(path: Path) -> dict[str, int]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        profile = raw["profiles"]["S8"]
        page_count = profile["page_count"]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid S8 fixture contract: {path}") from error
    if page_count != 8:
        raise ValueError("S8 fixture contract must define exactly eight pages")
    return {"page_count": page_count}


def _create_props(project_root: Path, page_count: int) -> ProjectVideoProps:
    pages: list[VideoPageProps] = []
    project_id = uuid5(NAMESPACE_URL, f"performance-cache:{project_root.as_posix()}")
    inputs = project_root / "inputs"
    for page_order in range(1, page_count + 1):
        image_path = inputs / f"page-{page_order:04d}.png"
        _write_page_image(image_path, page_order, variant=0)
        pages.append(
            VideoPageProps(
                page_id=uuid5(project_id, f"page-{page_order}"),
                page_order=page_order,
                title=f"S8 page {page_order}",
                image_path=str(image_path.relative_to(project_root)),
                audio_path=f"audio/page-{page_order:04d}.wav",
                start_ms=(page_order - 1) * 1_000,
                end_ms=page_order * 1_000,
            )
        )
    return ProjectVideoProps(
        project_id=project_id,
        duration_ms=page_count * 1_000,
        template_version="performance-cache-s8-v1",
        pages=pages,
    )


def _write_page_image(path: Path, page_order: int, *, variant: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    color = (
        (page_order * 29 + variant * 97) % 256,
        (page_order * 53 + variant * 71) % 256,
        (page_order * 83 + variant * 43) % 256,
    )
    Image.new("RGB", (640, 360), color).save(path, format="PNG")


def _run_phase(
    name: str, service: VideoRenderService, props: ProjectVideoProps
) -> CachePhaseEvidence:
    started = time.perf_counter()
    rendered = service.render_pages(props)
    duration_ms = round((time.perf_counter() - started) * 1_000)
    artifacts = tuple(_artifact(item) for item in rendered)
    return CachePhaseEvidence(
        name=name,
        duration_ms=duration_ms,
        cache_hits=sum(item.cached for item in rendered),
        cache_misses=sum(not item.cached for item in rendered),
        page_graph_hash=_page_graph_hash(rendered),
        artifacts=artifacts,
    )


def _artifact(rendered: RenderedPage) -> PageCacheArtifact:
    return PageCacheArtifact(
        page_order=rendered.page_order,
        cached=rendered.cached,
        cache_key=rendered.cache_key,
        artifact_sha256=sha256_file(rendered.path),
        artifact_size_bytes=rendered.path.stat().st_size,
    )


def _page_graph_hash(rendered: list[RenderedPage]) -> str:
    payload = [
        {"page_order": item.page_order, "cache_key": item.cache_key}
        for item in sorted(rendered, key=lambda item: item.page_order)
    ]
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _validate_cycle(cycle: CacheCycleEvidence, page_count: int) -> None:
    if (cycle.cold.cache_hits, cycle.cold.cache_misses) != (0, page_count):
        raise RuntimeError("cold cache cycle did not render every page")
    if (cycle.warm.cache_hits, cycle.warm.cache_misses) != (page_count, 0):
        raise RuntimeError("warm cache cycle did not reuse every page")
    if (cycle.selective_invalidation.cache_hits, cycle.selective_invalidation.cache_misses) != (
        page_count - 1,
        1,
    ):
        raise RuntimeError("selective invalidation did not rerender exactly one page")
    if cycle.cold.page_graph_hash != cycle.warm.page_graph_hash:
        raise RuntimeError("warm cache cycle changed the page graph hash")
    if cycle.warm.page_graph_hash == cycle.selective_invalidation.page_graph_hash:
        raise RuntimeError("selective invalidation did not change the page graph hash")

    cold = {item.page_order: item for item in cycle.cold.artifacts}
    warm = {item.page_order: item for item in cycle.warm.artifacts}
    selective = {item.page_order: item for item in cycle.selective_invalidation.artifacts}
    for page_order in range(1, page_count + 1):
        if cold[page_order].artifact_sha256 != warm[page_order].artifact_sha256:
            raise RuntimeError("warm cache artifact changed without an input change")
        if page_order == cycle.changed_page_order:
            if cold[page_order].artifact_sha256 == selective[page_order].artifact_sha256:
                raise RuntimeError("changed page did not produce a new artifact")
        elif cold[page_order].artifact_sha256 != selective[page_order].artifact_sha256:
            raise RuntimeError("unchanged page artifact changed during selective invalidation")


def _cycle_payload(cycle: CacheCycleEvidence) -> dict[str, object]:
    return {
        "cold": _phase_payload(cycle.cold),
        "warm": _phase_payload(cycle.warm),
        "selective_invalidation": _phase_payload(cycle.selective_invalidation),
        "mutation": {
            "changed_page_order": cycle.changed_page_order,
            "source_before_sha256": cycle.source_before_sha256,
            "source_after_sha256": cycle.source_after_sha256,
        },
    }


def _phase_payload(phase: CachePhaseEvidence) -> dict[str, object]:
    payload = asdict(phase)
    payload["artifacts"] = [asdict(item) for item in phase.artifacts]
    return payload


def _write_new_json(path: Path, value: object) -> None:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(serialized)
