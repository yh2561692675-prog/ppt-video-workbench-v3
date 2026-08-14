# PyInstaller entry-point contract for the Windows release build.
# The build script supplies the pinned runtime, Web assets, Remotion bundle,
# FFmpeg/FFprobe, LibreOffice and OCR resources into the release directory.
# ruff: noqa: F821 - PyInstaller injects the spec globals at build time.

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

project_root = Path(SPECPATH).parents[1]
api_entry = project_root / "apps" / "api" / "src" / "workbench" / "desktop.py"


def find_visual_cpp_runtime_binaries() -> list[tuple[str, str]]:
    """Bundle VC runtime DLLs so a clean Windows host can load python312.dll."""
    runtime_names = (
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "msvcp140.dll",
        "msvcp140_1.dll",
        "msvcp140_2.dll",
    )
    required_names = {
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "msvcp140.dll",
    }
    search_roots = [
        Path(sys.base_prefix),
        Path(sys.prefix),
        Path(sys.executable).parent,
    ]
    system_root = os.environ.get("SystemRoot")
    if system_root:
        search_roots.append(Path(system_root) / "System32")
    search_roots.extend(
        Path(entry)
        for entry in os.environ.get("PATH", "").split(os.pathsep)
        if entry
    )

    binaries: list[tuple[str, str]] = []
    missing_required: list[str] = []
    for runtime_name in runtime_names:
        runtime_path = next(
            (
                root / runtime_name
                for root in search_roots
                if (root / runtime_name).is_file()
            ),
            None,
        )
        if runtime_path is None:
            if runtime_name in required_names:
                missing_required.append(runtime_name)
            continue
        binaries.append((str(runtime_path), "."))

    if missing_required:
        missing = ", ".join(missing_required)
        raise SystemExit(
            "Visual C++ runtime DLLs were not found on the Windows build host: "
            f"{missing}"
        )
    return binaries


binaries = find_visual_cpp_runtime_binaries()
faster_whisper_datas, faster_whisper_binaries, faster_whisper_hiddenimports = collect_all(
    "faster_whisper"
)
ctranslate2_datas, ctranslate2_binaries, ctranslate2_hiddenimports = collect_all("ctranslate2")

analysis = Analysis(
    [str(api_entry)],
    pathex=[str(project_root / "apps" / "api" / "src")],
    datas=faster_whisper_datas + ctranslate2_datas,
    binaries=binaries + faster_whisper_binaries + ctranslate2_binaries,
    hiddenimports=[
        "workbench",
        *faster_whisper_hiddenimports,
        *ctranslate2_hiddenimports,
    ],
    name="workbench",
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="workbench",
    console=True,
    contents_directory="_internal",
)
collect = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="workbench",
)
