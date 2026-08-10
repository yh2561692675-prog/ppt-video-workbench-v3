from __future__ import annotations

from pathlib import Path

import pytest


def _runtime(root: Path) -> Path:
    files = (
        "node/node.exe",
        "remotion/node_modules/@remotion/cli/remotion-cli.js",
        "remotion/src/index.ts",
        "ffmpeg/ffmpeg.exe",
        "ffmpeg/ffprobe.exe",
    )
    for relative_path in files:
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative_path, encoding="utf-8")
    return root


def test_renderer_runtime_resolves_all_packaged_components(tmp_path: Path) -> None:
    from workbench.runtime.layout import RuntimeLayout

    runtime = RuntimeLayout(_runtime(tmp_path / "runtime")).require_renderer()

    assert runtime.node_executable.name == "node.exe"
    assert runtime.remotion_cli.name == "remotion-cli.js"
    assert runtime.remotion_entry.as_posix().endswith("remotion/src/index.ts")
    assert runtime.ffmpeg_executable.name == "ffmpeg.exe"
    assert runtime.ffprobe_executable.name == "ffprobe.exe"


def test_renderer_runtime_reports_missing_packaged_component(tmp_path: Path) -> None:
    from workbench.runtime.layout import RuntimeComponentMissingError, RuntimeLayout

    root = _runtime(tmp_path / "runtime")
    (root / "ffmpeg/ffprobe.exe").unlink()

    with pytest.raises(RuntimeComponentMissingError, match="ffprobe"):
        RuntimeLayout(root).require_renderer()
