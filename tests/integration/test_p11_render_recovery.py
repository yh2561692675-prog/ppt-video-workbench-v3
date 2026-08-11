from __future__ import annotations

from pathlib import Path

from peripheral_host.module_runner import _copy_render_recovery


def test_render_recovery_copies_cache_and_segments_but_skips_untrusted_files(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    (source / "segments").mkdir(parents=True)
    (source / "page-cache.json").write_text("{}", encoding="utf-8")
    (source / "segments" / "page-0001.mp4").write_bytes(b"segment")
    (source / "run.exe").write_bytes(b"untrusted")

    _copy_render_recovery(source, destination)

    assert (destination / "page-cache.json").is_file()
    assert (destination / "segments" / "page-0001.mp4").is_file()
    assert not (destination / "run.exe").exists()
