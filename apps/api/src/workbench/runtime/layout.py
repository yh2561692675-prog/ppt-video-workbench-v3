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
    candidates = (
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
