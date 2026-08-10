from __future__ import annotations

import hashlib
import subprocess
import wave
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from workbench.audio.ffmpeg import AudioNormalizationError, normalize_audio
from workbench.audio.importer import AudioImportError, AudioImportService
from workbench.main import create_app
from workbench.services.project_service import ProjectService


def _make_fixture(path: Path, *, channels: int, sample_rate: int, silence: bool = False) -> None:
    source = (
        f"anullsrc=r={sample_rate}:cl={'mono' if channels == 1 else 'stereo'}"
        if silence
        else f"sine=frequency=880:sample_rate={sample_rate}"
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            source,
            "-t",
            "1.2",
            "-ac",
            str(channels),
            "-y",
            str(path),
        ],
        check=True,
    )


@pytest.mark.parametrize("suffix", [".wav", ".mp3"])
def test_normalizes_supported_audio_and_preserves_original(tmp_path: Path, suffix: str) -> None:
    original = tmp_path / f"中文 录音{suffix}"
    _make_fixture(original, channels=2, sample_rate=44_100)
    before = hashlib.sha256(original.read_bytes()).hexdigest()

    result = normalize_audio(original, tmp_path / "normalized")

    assert original.exists()
    assert hashlib.sha256(original.read_bytes()).hexdigest() == before
    assert result.wav_path.exists()
    assert result.wav_path != original
    assert result.sample_rate == 16_000
    assert result.channels == 1
    assert 1_150 <= result.duration_ms <= 1_250
    assert result.sha256 == hashlib.sha256(result.wav_path.read_bytes()).hexdigest()
    assert result.quality.peak_dbfs > -30
    assert result.command_summary == "ffmpeg normalize -> pcm_s16le/16000Hz/mono"
    with wave.open(str(result.wav_path), "rb") as handle:
        assert handle.getframerate() == 16_000
        assert handle.getnchannels() == 1


def test_marks_abnormal_silence_for_confirmation(tmp_path: Path) -> None:
    original = tmp_path / "silent.wav"
    _make_fixture(original, channels=1, sample_rate=16_000, silence=True)

    result = normalize_audio(original, tmp_path / "normalized")

    assert result.quality.needs_confirmation is True
    assert result.quality.silence_ratio >= 0.99
    assert result.quality.silence_intervals_ms == [(0, result.duration_ms)]


def test_rejects_corrupt_audio_without_leaving_partial_output(tmp_path: Path) -> None:
    original = tmp_path / "broken.mp3"
    original.write_bytes(b"not an audio stream")
    output = tmp_path / "normalized"

    with pytest.raises(AudioNormalizationError, match="无法读取或转换音频"):
        normalize_audio(original, output)

    assert not list(output.glob("*.wav")) if output.exists() else True


def test_rejects_audio_above_configured_size_limit_without_writing(tmp_path: Path) -> None:
    projects = ProjectService(tmp_path / "workspace")
    project = projects.create("超长录音")

    with pytest.raises(AudioImportError, match="超过大小限制"):
        AudioImportService(projects, max_bytes=4).import_bytes(project.id, "too-long.wav", b"12345")

    project_dir = projects.workspace_root / project.project_dir
    assert not (project_dir / "05_音频" / "原始录音").exists()
    projects.close()


def test_audio_import_api_copies_original_persists_analysis_and_reopens(tmp_path: Path) -> None:
    fixture = tmp_path / "voice.mp3"
    _make_fixture(fixture, channels=2, sample_rate=44_100)
    app = create_app(tmp_path / "workspace")
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "音频导入"}).json()["data"]
        response = client.post(
            f"/api/projects/{project['id']}/audio/import",
            files={"file": ("本人录音.mp3", fixture.read_bytes(), "audio/mpeg")},
        )
        assert response.status_code == 201
        imported = response.json()["data"]
        assert imported["original_relative_path"].startswith("05_音频/原始录音/")
        assert imported["normalized_relative_path"].endswith(".normalized.wav")
        assert imported["sample_rate"] == 16_000
        assert imported["channels"] == 1

        reopened = client.get(f"/api/projects/{project['id']}").json()["data"]
        assert reopened["audio_import"] == imported
        project_dir = tmp_path / "workspace" / reopened["project_dir"]
        saved_original = project_dir / imported["original_relative_path"]
        assert saved_original.read_bytes() == fixture.read_bytes()
        assert (project_dir / imported["normalized_relative_path"]).exists()
        assert any(event["action"] == "local_audio_imported" for event in reopened["audit_log"])
