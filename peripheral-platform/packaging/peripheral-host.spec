# PyInstaller one-directory contract for the S0 peripheral host.

from pathlib import Path

project_root = Path(SPECPATH).parents[1]
platform_root = project_root / "peripheral-platform"
source_root = platform_root / "src"
entry_point = source_root / "peripheral_host" / "__main__.py"

datas = [
    (str(path), "schemas") for path in sorted((platform_root / "schemas").glob("*.json"))
]
datas.extend(
    (str(path), "migrations")
    for path in sorted((platform_root / "migrations").glob("*.sql"))
)

analysis = Analysis(
    [str(entry_point)],
    pathex=[str(source_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "peripheral_contracts",
        "peripheral_host",
        "peripheral_modules.echo",
        "peripheral_modules.echo.__main__",
    ],
    name="peripheral-host",
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="peripheral-host",
    console=True,
    contents_directory=".",
)
collect = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="peripheral",
)
