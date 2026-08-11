from __future__ import annotations

import sys
from pathlib import Path

import pytest
from workbench.platform.composition import create_platform_services
from workbench.platform.local import LocalAtomicFileService, LocalPathService, LocalProcessService
from workbench.platform.models import PlatformPathError


def test_logical_paths_are_portable_and_contained(tmp_path: Path) -> None:
    paths = LocalPathService(tmp_path)
    target = paths.logical_to_local("materials/slides.pptx")
    assert target == (tmp_path / "workspace-data" / "materials" / "slides.pptx").resolve()
    with pytest.raises(PlatformPathError):
        paths.logical_to_local("../outside.txt")
    with pytest.raises(PlatformPathError):
        paths.logical_to_local("C:/outside.txt")
    with pytest.raises(PlatformPathError):
        paths.directory("unknown")


def test_atomic_file_write_survives_replace(tmp_path: Path) -> None:
    paths = LocalPathService(tmp_path)
    files = LocalAtomicFileService(paths)
    target = paths.logical_to_local("cache/state.json", root="cache")
    files.write_bytes(target, b"first")
    files.write_bytes(target, b"second")
    assert files.read_bytes(target) == b"second"
    assert not list(target.parent.glob(f".{target.name}.*"))


def test_process_service_uses_argument_array_and_enforces_timeout(tmp_path: Path) -> None:
    runner = LocalProcessService()
    ok = runner.run([sys.executable, "-c", "print('safe')"], cwd=tmp_path)
    assert ok.return_code == 0
    assert ok.stdout.strip() == "safe"
    timed = runner.run([sys.executable, "-c", "import time; time.sleep(2)"], timeout_ms=50)
    assert timed.timed_out is True
    assert timed.return_code != 0


def test_composition_root_returns_capability_snapshot(tmp_path: Path) -> None:
    services = create_platform_services(tmp_path)
    snapshot = services.capabilities()
    assert snapshot.info.platform in {"windows", "macos", "linux"}
    assert snapshot.fingerprint.startswith("sha256:")
    assert snapshot.info.platform == "windows" if sys.platform == "win32" else True
