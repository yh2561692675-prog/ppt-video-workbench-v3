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


def test_renderer_runtime_resolves_all_packaged_components(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from workbench.runtime.layout import RuntimeLayout

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local-app-data"))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "program-files"))
    monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path / "program-files-x86"))
    monkeypatch.delenv("WORKBENCH_REMOTION_BROWSER_EXECUTABLE", raising=False)
    runtime = RuntimeLayout(_runtime(tmp_path / "runtime")).require_renderer()

    assert runtime.node_executable.name == "node.exe"
    assert runtime.remotion_cli.name == "remotion-cli.js"
    assert runtime.remotion_entry.as_posix().endswith("remotion/src/index.ts")
    assert runtime.ffmpeg_executable.name == "ffmpeg.exe"
    assert runtime.ffprobe_executable.name == "ffprobe.exe"


def test_renderer_runtime_prefers_local_playwright_chromium(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from workbench.runtime.layout import RuntimeLayout

    local_app_data = tmp_path / "local-app-data"
    browser = local_app_data / "ms-playwright" / "chromium-1193" / "chrome-win" / "chrome.exe"
    browser.parent.mkdir(parents=True)
    browser.write_text("chromium", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path / "program-files"))
    monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path / "program-files-x86"))
    monkeypatch.delenv("WORKBENCH_REMOTION_BROWSER_EXECUTABLE", raising=False)

    runtime = RuntimeLayout(_runtime(tmp_path / "runtime")).require_renderer()

    assert runtime.browser_executable == browser.resolve()


def test_renderer_runtime_reports_missing_packaged_component(tmp_path: Path) -> None:
    from workbench.runtime.layout import RuntimeComponentMissingError, RuntimeLayout

    root = _runtime(tmp_path / "runtime")
    (root / "ffmpeg/ffprobe.exe").unlink()

    with pytest.raises(RuntimeComponentMissingError, match="ffprobe"):
        RuntimeLayout(root).require_renderer()
