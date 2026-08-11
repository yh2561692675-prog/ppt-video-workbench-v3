from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from workbench.rendering.legacy_adapter import (
    LegacyFallbackForbidden,
    LegacyProjectAdapter,
)


def _materialize_fixture(root: Path) -> dict[str, object]:
    fixture = json.loads(
        Path("tests/fixtures/legacy-project-v1.json").read_text(encoding="utf-8")
    )
    root.mkdir()
    for relative, contents in fixture["files"].items():
        path = root.joinpath(*relative.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents.encode("utf-8"))
    manifest = fixture["manifest"]
    (root / "project.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )
    return manifest


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_legacy_adapter_is_deterministic_read_only_and_reports_damage(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    _materialize_fixture(root)
    before = _tree_hashes(root)
    adapter = LegacyProjectAdapter(root)

    first = adapter.open_manifest(root / "project.json")
    second = adapter.open_manifest(root / "project.json")
    after = _tree_hashes(root)

    assert before == after
    assert first.timeline.content_hash == second.timeline.content_hash
    assert [clip.id for clip in first.timeline.tracks[0].clips] == [
        clip.id for clip in second.timeline.tracks[0].clips
    ]
    assert [clip.payload["normalized_order"] for clip in first.timeline.tracks[0].clips] == [
        1,
        2,
        3,
    ]
    assert any(asset.legacy_snapshot for asset in first.assets)
    assert first.subtitles.cues[0].text == "匿名字幕"
    codes = {issue.code for issue in first.issues}
    assert {
        "legacy_duplicate_page_order",
        "legacy_absolute_path_outside_project",
        "legacy_page_media_missing",
        "legacy_page_audio_missing",
    } <= codes
    assert "08_output/legacy-final.mp4" in first.source_hashes
    fixture = json.loads(
        Path("tests/fixtures/legacy-project-v1.json").read_text(encoding="utf-8")
    )
    assert {
        path: first.source_hashes[path]
        for path in fixture["expected_sha256"]
        if path in first.source_hashes
    } == {
        path: digest
        for path, digest in fixture["expected_sha256"].items()
        if path in first.source_hashes
    }


def test_v2_exclusive_project_never_silently_falls_back(tmp_path: Path) -> None:
    root = tmp_path / "legacy"
    payload = _materialize_fixture(root)

    with pytest.raises(LegacyFallbackForbidden, match="cannot silently fall back"):
        LegacyProjectAdapter(root).open(payload, renderer_generation="v2")
