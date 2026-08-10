# PyInstaller one-directory contract for the S0 peripheral host.

from pathlib import Path

project_root = Path(SPECPATH).parents[1]
platform_root = project_root / "peripheral-platform"
source_root = platform_root / "src"
workbench_source_root = project_root / "apps" / "api" / "src"
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
    pathex=[str(source_root), str(workbench_source_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "peripheral_contracts",
        "peripheral_host",
        "peripheral_modules.echo",
        "peripheral_modules.echo.__main__",
        "workbench.business_modules.registry",
        "workbench.business_modules.runtime",
        "workbench.business_modules.p03_material.__main__",
        "workbench.business_modules.p04_extract.__main__",
        "workbench.business_modules.p05_match.__main__",
        "workbench.business_modules.p06_narration.__main__",
        "workbench.business_modules.p07_audio.__main__",
        "workbench.business_modules.p08_subtitle.__main__",
        "workbench.business_modules.p09_effects.__main__",
        "workbench.business_modules.p10_preflight.__main__",
        "workbench.business_modules.p11_render.__main__",
        "workbench.business_modules.p12_delivery.__main__",
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
