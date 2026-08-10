import importlib.util
from pathlib import Path


def _load_stage_module(repository_root: Path):
    module_path = repository_root / "scripts" / "stage_pyinstaller_onedir.py"
    spec = importlib.util.spec_from_file_location("stage_pyinstaller_onedir", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stage_onedir_bundle_promotes_the_complete_runtime_tree(tmp_path: Path) -> None:
    """Leaving the onedir bundle nested must break the release staging contract."""
    repository_root = Path(__file__).parents[2]
    module = _load_stage_module(repository_root)
    source = tmp_path / "pyinstaller-dist" / "workbench"
    destination = tmp_path / "release" / "api"
    runtime = source / "_internal"
    runtime.mkdir(parents=True)
    destination.mkdir(parents=True)

    (source / "workbench.exe").write_bytes(b"exe")
    for dll_name in (
        "python312.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "msvcp140.dll",
    ):
        (runtime / dll_name).write_bytes(dll_name.encode("ascii"))

    module.stage_onedir_bundle(source, destination)

    assert (destination / "workbench.exe").read_bytes() == b"exe"
    for dll_name in (
        "python312.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "msvcp140.dll",
    ):
        assert (destination / "_internal" / dll_name).read_bytes() == dll_name.encode("ascii")
    assert not source.exists()
