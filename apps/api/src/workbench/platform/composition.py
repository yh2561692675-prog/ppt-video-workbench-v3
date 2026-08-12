"""PlatformServices composition root."""

from __future__ import annotations

import platform as platform_module
import sys
from pathlib import Path
from typing import Literal

from .local import LocalPlatformServices


def create_platform_services(
    base_dir: Path,
    *,
    app_version: str = "0.1.1",
    platform_override: Literal["windows", "macos", "linux"] | None = None,
) -> LocalPlatformServices:
    platform_name: Literal["windows", "macos", "linux"]
    if platform_override is not None:
        platform_name = platform_override
    elif sys.platform == "win32":
        platform_name = "windows"
    elif sys.platform == "darwin":
        platform_name = "macos"
    elif sys.platform.startswith("linux"):
        platform_name = "linux"
    else:
        raise RuntimeError(f"unsupported platform: {sys.platform}")
    return LocalPlatformServices(
        base_dir,
        app_version=app_version,
        platform=platform_name,
        architecture=platform_module.machine().lower() or "unknown",
    )
