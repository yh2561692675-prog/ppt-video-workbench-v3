from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


class RuntimeComponentMissingError(RuntimeError):
    pass


@dataclass(frozen=True)
class RendererRuntime:
    root: Path
    node_executable: Path
    remotion_cli: Path
    remotion_entry: Path
    ffmpeg_executable: Path
    ffprobe_executable: Path
    browser_executable: Path | None


class RuntimeLayout:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    @classmethod
    def from_environment(cls) -> RuntimeLayout:
        configured = os.environ.get("WORKBENCH_RUNTIME_ROOT")
        if configured:
            return cls(Path(configured))
        if getattr(sys, "frozen", False):
            return cls(Path(sys.executable).resolve().parent.parent / "runtime")
        raise RuntimeComponentMissingError(
            "未设置 WORKBENCH_RUNTIME_ROOT，无法定位已打包的渲染运行时"
        )

    def require_renderer(self) -> RendererRuntime:
        required = {
            "node": self.root / "node" / "node.exe",
            "remotion-cli": self.root
            / "remotion"
            / "node_modules"
            / "@remotion"
            / "cli"
            / "remotion-cli.js",
            "remotion-entry": self.root / "remotion" / "src" / "index.ts",
            "ffmpeg": self.root / "ffmpeg" / "ffmpeg.exe",
            "ffprobe": self.root / "ffmpeg" / "ffprobe.exe",
        }
        missing = [name for name, path in required.items() if not path.is_file()]
        if missing:
            names = ", ".join(missing)
            raise RuntimeComponentMissingError(
                f"已打包的渲染运行时缺少组件：{names}。"
                "请重新运行 prepare-runtime.ps1 并重建安装包。"
            )
        browser = _browser_executable()
        return RendererRuntime(
            root=self.root,
            node_executable=required["node"],
            remotion_cli=required["remotion-cli"],
            remotion_entry=required["remotion-entry"],
            ffmpeg_executable=required["ffmpeg"],
            ffprobe_executable=required["ffprobe"],
            browser_executable=browser,
        )


def _browser_executable() -> Path | None:
    configured = os.environ.get("WORKBENCH_REMOTION_BROWSER_EXECUTABLE")
    if configured:
        path = Path(configured).expanduser().resolve()
        return path if path.is_file() else None
    # Prefer a Chromium build that is known to support Remotion's
    # "chrome-for-testing" launch contract. Some managed Edge installs
    # accept the normal GUI launch but exit immediately when started with the
    # isolated headless flags used by Remotion. Playwright keeps its browser
    # under the per-user LocalAppData directory, so this fallback remains
    # machine-local and does not require a network download at export time.
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        playwright_root = Path(local_app_data) / "ms-playwright"
        chromium_candidates = sorted(
            (
                version / "chrome-win" / "chrome.exe"
                for version in playwright_root.glob("chromium-*")
                if (version / "chrome-win" / "chrome.exe").is_file()
            ),
            reverse=True,
        )
        if chromium_candidates:
            return chromium_candidates[0].resolve()
    # Fall back to the installed browsers used by ordinary Windows hosts.
    # The explicit Chromium candidates above are intentionally checked first
    # because they are compatible with the pinned Remotion launch mode.
    candidates = (
        Path(os.environ.get("PROGRAMFILES", r"C:\\Program Files"))
        / "Google"
        / "Chrome"
        / "Application"
        / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\\Program Files (x86)"))
        / "Google"
        / "Chrome"
        / "Application"
        / "chrome.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\\Program Files"))
        / "Microsoft"
        / "Edge"
        / "Application"
        / "msedge.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\\Program Files (x86)"))
        / "Microsoft"
        / "Edge"
        / "Application"
        / "msedge.exe",
    )
    return next((path for path in candidates if path.is_file()), None)
