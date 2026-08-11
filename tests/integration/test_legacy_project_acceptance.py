from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

import pytest

REPOSITORY_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))


def _legacy_project(root: Path) -> Path:
    root.mkdir()
    (root / "05_audio").mkdir()
    (root / "06_subtitles").mkdir()
    (root / "05_audio" / "page-0001.wav").write_bytes(b"audio")
    (root / "06_subtitles" / "subtitles.srt").write_text("1\n", encoding="utf-8")
    (root / "project.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": str(uuid4()),
                "pages": [{"audio": {"relative_path": "05_audio/page-0001.wav"}}],
                "subtitle_artifact": {"srt_relative_path": "06_subtitles/subtitles.srt"},
            }
        ),
        encoding="utf-8",
    )
    return root


def test_legacy_project_copy_preserves_project_identity_and_media_hashes(tmp_path: Path) -> None:
    from scripts.windows_acceptance.legacy_project import (
        copy_and_verify_legacy_project,
        verify_legacy_copy,
    )

    source = _legacy_project(tmp_path / "source")
    record = copy_and_verify_legacy_project(source, tmp_path / "candidate-copy")
    verified = verify_legacy_copy(tmp_path / "candidate-copy")

    assert record["source_summary"]["project_id"] == verified["project_id"]
    assert record["source_summary"]["protected_files"] == verified["protected_files"]
    assert (source / "legacy-copy-manifest.json").exists() is False


def test_legacy_copy_detects_protected_media_change(tmp_path: Path) -> None:
    from scripts.windows_acceptance.legacy_project import (
        LegacyProjectError,
        copy_and_verify_legacy_project,
        verify_legacy_copy,
    )

    source = _legacy_project(tmp_path / "source")
    copy_and_verify_legacy_project(source, tmp_path / "candidate-copy")
    (tmp_path / "candidate-copy" / "05_audio" / "page-0001.wav").write_bytes(b"changed")

    with pytest.raises(LegacyProjectError, match="legacy_protected_file_changed"):
        verify_legacy_copy(tmp_path / "candidate-copy")
