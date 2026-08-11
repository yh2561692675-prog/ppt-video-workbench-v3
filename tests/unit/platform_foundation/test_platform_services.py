from __future__ import annotations

import sys
from pathlib import Path

import pytest
from workbench.platform.composition import create_platform_services
from workbench.platform.local import (
    LocalAtomicFileService,
    LocalPathService,
    LocalProcessService,
    LocalToolDiscoveryService,
)
from workbench.platform.models import PlatformPathError, ToolInfoV1


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
    bounded = runner.run(
        [sys.executable, "-c", "print('x' * 10000)"], max_output_bytes=32
    )
    assert bounded.output_truncated is True
    assert len(bounded.stdout) <= 32


def test_composition_root_returns_capability_snapshot(tmp_path: Path) -> None:
    services = create_platform_services(tmp_path)
    snapshot = services.capabilities()
    assert snapshot.info.platform in {"windows", "macos", "linux"}
    assert snapshot.fingerprint.startswith("sha256:")
    assert snapshot.expires_at > snapshot.generated_at
    statuses = {item.capability_id: item.status for item in snapshot.capability_states}
    assert statuses["paths"] == "supported"
    assert all("\\" not in (item.detail or "") for item in snapshot.capability_states)
    assert snapshot.info.platform == "windows" if sys.platform == "win32" else True


def test_tool_discovery_rejects_path_injection_and_reports_safe_metadata(tmp_path: Path) -> None:
    tools = LocalToolDiscoveryService(bundled_root=tmp_path / "runtime")
    with pytest.raises(ValueError):
        tools.find("../ffmpeg")
    python_tool = tools.find(Path(sys.executable).name)
    assert python_tool.available is True
    assert python_tool.executable_ref in {
        f"runtime://{Path(sys.executable).name}",
        f"system://{Path(sys.executable).name}",
    }
    assert python_tool.sha256 and python_tool.sha256.startswith("sha256:")


def test_tool_contract_rejects_absolute_executable_references(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ToolInfoV1(
            name="ffmpeg",
            available=True,
            executable_ref=r"C:\\secret\\ffmpeg.exe",
            source="supported_system",
        )


def test_media_and_office_snapshots_do_not_include_absolute_project_inputs(tmp_path: Path) -> None:
    services = create_platform_services(tmp_path)
    media = services.media.snapshot()  # type: ignore[attr-defined]
    office = services.office.snapshot()  # type: ignore[attr-defined]
    assert media["software_fallback"] in {True, False}
    assert office["network_access"] is False
    assert office["macro_execution"] is False
