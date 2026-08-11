# PyInstaller no-console bootstrap for the packaged desktop launcher.
# ruff: noqa: F821

from pathlib import Path

project_root = Path(SPECPATH).parents[1]
launcher_entry = project_root / "apps" / "api" / "src" / "workbench" / "desktop" / "launcher.py"

analysis = Analysis(
    [str(launcher_entry)],
    pathex=[str(project_root / "apps" / "api" / "src")],
    datas=[],
    binaries=[],
    hiddenimports=["workbench.desktop.release_slots"],
    name="workbench-launcher",
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    name="workbench-launcher",
    console=False,
)
