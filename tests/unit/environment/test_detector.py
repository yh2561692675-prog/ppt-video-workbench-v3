from __future__ import annotations

import zipfile
from pathlib import Path

from workbench.environment.detector import EnvironmentDetector


def _probe(name: str) -> tuple[str | None, str | None]:
    components = {
        "python": ("3.12.4", "C:/Runtime/python.exe"),
        "node": ("20.11.0", "C:/Runtime/node.exe"),
        "remotion": ("4.0.340", "C:/Runtime/remotion"),
        "ffmpeg": ("6.1.1", "C:/Runtime/ffmpeg.exe"),
        "ffprobe": ("6.1.1", "C:/Runtime/ffprobe.exe"),
        "libreoffice": ("24.2.0", "C:/Runtime/soffice.exe"),
        "ocr": ("3.2.0", "C:/Runtime/ocr"),
        "browser": ("128.0.0", "C:/Runtime/chrome.exe"),
    }
    return components.get(name, (None, None))


def test_detector_reports_component_failures_with_actions(tmp_path: Path) -> None:
    def probe(name: str) -> tuple[str | None, str | None]:
        if name == "node":
            return "16.0.0", "C:/Runtime/node.exe"
        if name == "ffmpeg":
            return None, None
        return _probe(name)

    report = EnvironmentDetector(tmp_path, component_probe=probe).detect_environment()

    node = next(item for item in report.checks if item.name == "node")
    ffmpeg = next(item for item in report.checks if item.name == "ffmpeg")
    assert node.status == "incompatible"
    assert node.code == "component_version_incompatible"
    assert node.blocking is True
    assert node.action
    assert ffmpeg.status == "missing"
    assert ffmpeg.code == "component_missing"
    assert "prepare-runtime.ps1" in ffmpeg.action
    assert report.allowed is False


def test_detector_reports_disk_permission_and_chinese_path_failures(tmp_path: Path) -> None:
    report = EnvironmentDetector(
        tmp_path,
        component_probe=_probe,
        disk_probe=lambda _: (100, 1_000),
        path_probe=lambda _: False,
        writable_probe=lambda _: False,
    ).detect_environment()

    codes = {item.code for item in report.checks}
    assert "disk_space_low" in codes
    assert "workspace_not_writable" in codes
    assert "chinese_path_unsupported" in codes
    assert report.allowed is False


def test_diagnostic_package_contains_only_redacted_report_files(tmp_path: Path) -> None:
    detector = EnvironmentDetector(tmp_path, component_probe=_probe)
    report = detector.detect_environment()
    bundle = detector.create_diagnostic_package(report)

    with zipfile.ZipFile(tmp_path / bundle.relative_path) as archive:
        names = set(archive.namelist())
        contents = "\n".join(
            archive.read(name).decode("utf-8") for name in names if name.endswith((".json", ".md"))
        )
    assert names == {"environment-report.json", "environment-report.md", "README.txt"}
    assert "api_key" not in contents
    assert "Authorization" not in contents
    assert "C:/Runtime" not in contents
