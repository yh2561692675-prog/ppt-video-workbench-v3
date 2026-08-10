from pathlib import Path


def _execute_spec(spec_path: Path, monkeypatch, tmp_path: Path) -> dict[str, object]:
    system32 = tmp_path / "Windows" / "System32"
    system32.mkdir(parents=True)
    for dll_name in (
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "msvcp140.dll",
        "msvcp140_1.dll",
        "msvcp140_2.dll",
    ):
        (system32 / dll_name).write_bytes(b"test-runtime")
    monkeypatch.setenv("SystemRoot", str(tmp_path / "Windows"))

    calls: dict[str, object] = {}

    class FakeAnalysis:
        def __init__(self, *args, **kwargs):
            calls["analysis"] = {"args": args, "kwargs": kwargs}
            self.scripts = [("desktop", "desktop.py", "PYSOURCE")]
            self.pure = [("workbench", "workbench.py", "PYMODULE")]
            self.binaries = [("python312.dll", "python312.dll", "BINARY")]
            self.datas = [("base_library.zip", "base_library.zip", "DATA")]

    class FakePyz:
        def __init__(self, *args, **kwargs):
            calls["pyz"] = {"args": args, "kwargs": kwargs}

    class FakeExe:
        def __init__(self, *args, **kwargs):
            calls["exe"] = {"object": self, "args": args, "kwargs": kwargs}

    class FakeCollect:
        def __init__(self, *args, **kwargs):
            calls["collect"] = {"args": args, "kwargs": kwargs}

    namespace = {
        "SPECPATH": str(spec_path.parent),
        "Analysis": FakeAnalysis,
        "PYZ": FakePyz,
        "EXE": FakeExe,
        "COLLECT": FakeCollect,
    }
    exec(  # noqa: S102 - the test intentionally executes the PyInstaller spec contract.
        compile(spec_path.read_text(encoding="utf-8"), spec_path, "exec"), namespace
    )
    return calls


def test_workbench_spec_builds_a_complete_onedir_payload(monkeypatch, tmp_path: Path) -> None:
    """Removing COLLECT or embedding binaries into EXE must break the release contract."""
    spec_path = Path(__file__).parents[2] / "apps" / "api" / "workbench.spec"

    calls = _execute_spec(spec_path, monkeypatch, tmp_path)

    exe_call = calls["exe"]
    assert exe_call["kwargs"]["exclude_binaries"] is True
    assert exe_call["kwargs"]["contents_directory"] == "_internal"

    collect_call = calls["collect"]
    analysis = calls["analysis"]
    assert analysis["kwargs"]["binaries"]
    assert collect_call["args"][1:] == (
        [("python312.dll", "python312.dll", "BINARY")],
        [("base_library.zip", "base_library.zip", "DATA")],
    )
    assert collect_call["kwargs"]["name"] == "workbench"
