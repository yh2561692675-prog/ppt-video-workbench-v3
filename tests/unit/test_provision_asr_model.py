from __future__ import annotations

from pathlib import Path

import pytest

from scripts.provision_asr_model import provision_model


def test_provision_model_switches_complete_snapshot_atomically(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def downloader(**kwargs: object) -> None:
        calls.append(kwargs)
        target = Path(str(kwargs["local_dir"]))
        (target / "config.json").write_text("{}", encoding="utf-8")
        (target / "model.bin").write_bytes(b"model")

    target = provision_model(tmp_path, "small", downloader=downloader)

    assert target == (tmp_path / "small").resolve()
    assert (target / "config.json").is_file()
    assert (target / "model.bin").read_bytes() == b"model"
    assert not (tmp_path / ".small.download").exists()
    assert calls[0]["repo_id"] == "Systran/faster-whisper-small"


def test_provision_model_removes_incomplete_snapshot(tmp_path: Path) -> None:
    def downloader(**kwargs: object) -> None:
        target = Path(str(kwargs["local_dir"]))
        (target / "config.json").write_text("{}", encoding="utf-8")

    with pytest.raises(RuntimeError, match="incomplete"):
        provision_model(tmp_path, "small", downloader=downloader)

    assert not (tmp_path / "small").exists()
    assert not (tmp_path / ".small.download").exists()
