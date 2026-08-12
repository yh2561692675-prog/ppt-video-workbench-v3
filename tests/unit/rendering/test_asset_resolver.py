from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest
from workbench.assets.models import AssetKind, AssetRecord, LicenseRecord, LicenseStatus
from workbench.rendering.asset_resolver import AssetResolutionError, AssetResolver
from workbench.rendering.models import (
    GraphCanvas,
    MediaProbeMetadata,
    RenderGraphV2,
    ResolvedAsset,
)
from workbench.rendering.preflight import GraphPreflight


def _record(project_id, content_hash: str) -> AssetRecord:
    return AssetRecord(
        project_id=project_id,
        kind=AssetKind.IMAGE,
        content_hash=content_hash,
        relative_object_path="media/page.png",
        original_name="page.png",
        mime_type="image/png",
        size_bytes=3,
        license=LicenseRecord(status=LicenseStatus.CONFIRMED),
    )


def test_asset_resolver_uses_authoritative_revision_hash(tmp_path: Path) -> None:
    project_id = uuid4()
    path = tmp_path / "media" / "page.png"
    path.parent.mkdir()
    path.write_bytes(b"new")
    expected_hash = hashlib.sha256(b"old").hexdigest()
    record = _record(project_id, expected_hash)
    resolved = AssetResolver(tmp_path, [record], project_id=project_id).resolve("media/page.png")
    assert resolved.exists
    assert resolved.content_hash == expected_hash
    assert resolved.object_relative_path == "media/page.png"
    assert resolved.mime_type == "image/png"


def test_asset_resolver_reuses_a_verified_content_addressed_source_alias(tmp_path: Path) -> None:
    project_id = uuid4()
    first = tmp_path / "audio" / "page-001.wav"
    second = tmp_path / "audio" / "page-002.wav"
    first.parent.mkdir()
    first.write_bytes(b"identical narration")
    second.write_bytes(b"identical narration")
    record = AssetRecord(
        project_id=project_id,
        kind=AssetKind.AUDIO,
        content_hash=hashlib.sha256(b"identical narration").hexdigest(),
        relative_object_path="workspace-data/assets/audio.wav",
        original_name="audio/page-001.wav",
        mime_type="audio/wav",
        size_bytes=len(b"identical narration"),
        license=LicenseRecord(status=LicenseStatus.CONFIRMED),
    )

    resolved = AssetResolver(tmp_path, [record], project_id=project_id).resolve(
        "audio/page-002.wav", kind="narration"
    )

    assert resolved.asset_id == record.asset_id
    assert resolved.source_ref == "audio/page-002.wav"
    assert resolved.license_status == LicenseStatus.CONFIRMED.value


def test_asset_resolver_rejects_cross_project_records(tmp_path: Path) -> None:
    with pytest.raises(AssetResolutionError, match="another project"):
        AssetResolver(tmp_path, [_record(uuid4(), "0" * 64)], project_id=uuid4())


def test_asset_resolver_never_returns_path_outside_project(tmp_path: Path) -> None:
    resolved = AssetResolver(tmp_path).resolve("../../outside.wav", kind="audio")
    assert resolved.resolved_path is None
    assert not resolved.exists


def test_preflight_detects_replaced_file_against_resolved_revision(tmp_path: Path) -> None:
    project_id = uuid4()
    path = tmp_path / "media" / "page.png"
    path.parent.mkdir()
    path.write_bytes(b"new")
    record = _record(project_id, hashlib.sha256(b"old").hexdigest())
    asset = AssetResolver(tmp_path, [record], project_id=project_id).resolve("media/page.png")
    graph = RenderGraphV2(
        project_id=project_id,
        timeline_revision=1,
        duration_us=1_000_000,
        canvas=GraphCanvas(width=1920, height=1080, fps=30),
        assets=[asset],
        graph_hash="0" * 64,
    )
    report = GraphPreflight().check(graph, tmp_path, verify_hash=False)
    assert any(issue.code == "ASSET_HASH_MISMATCH" for issue in report.issues)


def test_preflight_blocks_asset_from_another_project(tmp_path: Path) -> None:
    project_id = uuid4()
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "page.png").write_bytes(b"page")
    graph = RenderGraphV2(
        project_id=project_id,
        timeline_revision=1,
        duration_us=1_000_000,
        canvas=GraphCanvas(width=1920, height=1080, fps=30),
        assets=[
            ResolvedAsset(
                project_id=uuid4(),
                kind="image",
                source_ref="media/page.png",
                resolved_path="media/page.png",
                exists=True,
                size_bytes=4,
            )
        ],
        graph_hash="0" * 64,
    )
    report = GraphPreflight().check(graph, tmp_path, verify_hash=False, strict_assets=False)
    assert any(issue.code == "ASSET_PROJECT_SCOPE" for issue in report.issues)


def test_media_probe_is_recorded_and_metadata_changes_are_blocked(tmp_path: Path) -> None:
    project_id = uuid4()
    path = tmp_path / "media" / "clip.mp4"
    path.parent.mkdir()
    path.write_bytes(b"video")
    record = AssetRecord(
        project_id=project_id,
        kind=AssetKind.VIDEO,
        content_hash=hashlib.sha256(b"video").hexdigest(),
        relative_object_path="media/clip.mp4",
        original_name="clip.mp4",
        mime_type="video/mp4",
        size_bytes=5,
        duration_us=2_000_000,
        width=1280,
        height=720,
        fps_num=30,
        fps_den=1,
        license=LicenseRecord(status=LicenseStatus.CONFIRMED),
    )
    resolved = AssetResolver(
        tmp_path,
        [record],
        project_id=project_id,
        media_probe=lambda _: {
            "streams": [
                {
                    "codec_type": "video",
                    "width": 1920,
                    "height": 1080,
                    "avg_frame_rate": "30000/1001",
                }
            ],
            "format": {"duration": "2.0"},
        },
    ).resolve("media/clip.mp4")
    assert resolved.media_probe_status == "verified"
    assert resolved.media_probe == MediaProbeMetadata(
        width=1920,
        height=1080,
        duration_us=2_000_000,
        fps_num=30000,
        fps_den=1001,
    )
    graph = RenderGraphV2(
        project_id=project_id,
        timeline_revision=1,
        duration_us=3_000_000,
        canvas=GraphCanvas(width=1920, height=1080, fps=30),
        assets=[resolved],
        graph_hash="0" * 64,
    )
    report = GraphPreflight().check(graph, tmp_path, verify_hash=False)
    assert any(issue.code == "ASSET_MEDIA_METADATA_MISMATCH" for issue in report.issues)


def test_asset_resolver_selects_mode_specific_proxy(tmp_path: Path) -> None:
    project_id = uuid4()
    source = tmp_path / "media" / "clip.mp4"
    interactive = tmp_path / "proxies" / "interactive.mp4"
    authoritative = tmp_path / "proxies" / "authoritative.mp4"
    source.parent.mkdir()
    interactive.parent.mkdir()
    source.write_bytes(b"source")
    interactive.write_bytes(b"interactive")
    authoritative.write_bytes(b"authoritative")
    parent = AssetRecord(
        project_id=project_id,
        kind=AssetKind.VIDEO,
        content_hash=hashlib.sha256(b"source").hexdigest(),
        relative_object_path="media/clip.mp4",
        original_name="clip.mp4",
        mime_type="video/mp4",
        size_bytes=6,
        license=LicenseRecord(status=LicenseStatus.CONFIRMED),
    )

    def derived(path: str, payload: bytes, tags: list[str]) -> AssetRecord:
        return AssetRecord(
            project_id=project_id,
            kind=AssetKind.VIDEO,
            content_hash=hashlib.sha256(payload).hexdigest(),
            relative_object_path=path,
            original_name=Path(path).name,
            mime_type="video/mp4",
            size_bytes=len(payload),
            license=LicenseRecord(status=LicenseStatus.CONFIRMED),
            derived_from=parent.asset_id,
            operation="proxy",
            tags=tags,
        )

    resolver = AssetResolver(
        tmp_path,
        [
            parent,
            derived("proxies/interactive.mp4", b"interactive", ["interactive_proxy"]),
            derived("proxies/authoritative.mp4", b"authoritative", ["authoritative_proxy"]),
        ],
        project_id=project_id,
        media_probe=lambda _: MediaProbeMetadata(duration_us=1_000_000),
    )
    assert resolver.resolve("media/clip.mp4", resolution_mode="interactive").resolved_path == (
        "proxies/interactive.mp4"
    )
    assert resolver.resolve("media/clip.mp4", resolution_mode="authoritative").resolved_path == (
        "proxies/authoritative.mp4"
    )
    final = resolver.resolve("media/clip.mp4", resolution_mode="final")
    assert final.resolved_path == "media/clip.mp4"
    assert final.proxy_relative_path is None


def test_unknown_in_project_path_becomes_explicit_legacy_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "legacy" / "old.wav"
    path.parent.mkdir()
    path.write_bytes(b"legacy")
    resolver = AssetResolver(tmp_path)
    first = resolver.resolve("legacy/old.wav", kind="audio")
    second = resolver.resolve("legacy/old.wav", kind="audio")
    assert first.legacy_snapshot
    assert first.asset_id == second.asset_id
    assert first.revision == 1
    assert first.resolved_path == "legacy/old.wav"
    assert first.content_hash == hashlib.sha256(b"legacy").hexdigest()
