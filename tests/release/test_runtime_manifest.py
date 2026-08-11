from __future__ import annotations

from pathlib import Path

import pytest
from workbench.release.manifest import (
    ReleaseManifestError,
    build_runtime_manifest,
    validate_runtime_manifest,
)


def _bundle(tmp_path: Path) -> tuple[Path, Path, Path]:
    release = tmp_path / "release"
    artifact = release / "app" / "workbench.exe"
    license_file = release / "licenses" / "python.txt"
    artifact.parent.mkdir(parents=True)
    license_file.parent.mkdir(parents=True)
    artifact.write_bytes(b"runtime-binary")
    license_file.write_text("Python license", encoding="utf-8")
    return release, artifact, license_file


def test_runtime_manifest_records_and_validates_hashes_and_licenses(tmp_path: Path) -> None:
    release, artifact, license_file = _bundle(tmp_path)
    manifest = build_runtime_manifest(
        release,
        artifact_paths=[(artifact, "python-runtime")],
        license_paths=[license_file],
        version="1.0.0",
    )

    assert validate_runtime_manifest(release, manifest).valid is True
    assert manifest.artifacts[0].relative_path == "app/workbench.exe"
    assert manifest.artifacts[0].sha256
    assert manifest.licenses[0].relative_path == "licenses/python.txt"


def test_runtime_manifest_rejects_missing_or_tampered_artifacts(tmp_path: Path) -> None:
    release, artifact, license_file = _bundle(tmp_path)
    manifest = build_runtime_manifest(
        release,
        artifact_paths=[(artifact, "python-runtime")],
        license_paths=[license_file],
        version="1.0.0",
    )
    artifact.write_bytes(b"tampered")

    validation = validate_runtime_manifest(release, manifest)
    assert validation.valid is False
    assert "artifact_hash_mismatch" in validation.codes


def test_runtime_manifest_rejects_license_gaps_and_development_secrets(
    tmp_path: Path,
) -> None:
    release, artifact, license_file = _bundle(tmp_path)
    artifact.write_text("API_KEY=dev-secret", encoding="utf-8")
    manifest = build_runtime_manifest(
        release,
        artifact_paths=[(artifact, "python-runtime")],
        license_paths=[],
        version="1.0.0",
    )

    validation = validate_runtime_manifest(release, manifest)
    assert validation.valid is False
    assert "license_inventory_empty" in validation.codes
    assert "development_secret_residue" in validation.codes

    with pytest.raises(ReleaseManifestError, match="许可证"):
        build_runtime_manifest(
            release,
            artifact_paths=[(artifact, "python-runtime")],
            license_paths=[],
            version="1.0.0",
            require_licenses=True,
        )


def test_runtime_manifest_allows_pinned_renderer_dependency_constants(
    tmp_path: Path,
) -> None:
    """Third-party Remotion code can contain public API constants without being user config."""
    release, artifact, license_file = _bundle(tmp_path)
    dependency = release / "runtime" / "remotion" / "node_modules" / "vendor" / "client.js"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("const API_KEY = 'public-dependency-constant';", encoding="utf-8")
    manifest = build_runtime_manifest(
        release,
        artifact_paths=[
            (artifact, "python-runtime"),
            (dependency, "renderer-runtime"),
        ],
        license_paths=[license_file],
        version="1.0.0",
    )

    assert validate_runtime_manifest(release, manifest).valid is True


def test_runtime_manifest_rejects_a_secret_in_application_remotion_source(
    tmp_path: Path,
) -> None:
    """Our own packaged Remotion source remains subject to the secret gate."""
    release, artifact, license_file = _bundle(tmp_path)
    source = release / "runtime" / "remotion" / "src" / "config.ts"
    source.parent.mkdir(parents=True)
    source.write_text("const API_KEY = 'dev-secret';", encoding="utf-8")
    manifest = build_runtime_manifest(
        release,
        artifact_paths=[
            (artifact, "python-runtime"),
            (source, "renderer-runtime"),
        ],
        license_paths=[license_file],
        version="1.0.0",
    )

    validation = validate_runtime_manifest(release, manifest)

    assert validation.valid is False
    assert "development_secret_residue" in validation.codes


def test_runtime_manifest_allows_risk_alert_css_identifiers(tmp_path: Path) -> None:
    release, artifact, license_file = _bundle(tmp_path)
    source = release / "runtime" / "remotion" / "src" / "effects" / "templates" / "RiskAlert.tsx"
    source.parent.mkdir(parents=True)
    source.write_text('<div className="risk-alert__title">Alert</div>', encoding="utf-8")
    manifest = build_runtime_manifest(
        release,
        artifact_paths=[
            (artifact, "python-runtime"),
            (source, "renderer-runtime"),
        ],
        license_paths=[license_file],
        version="1.0.0",
    )

    assert validate_runtime_manifest(release, manifest).valid is True


def test_runtime_manifest_rejects_long_openai_style_key(tmp_path: Path) -> None:
    release, artifact, license_file = _bundle(tmp_path)
    artifact.write_text("sk-1234567890abcdefghijklmnop", encoding="utf-8")
    manifest = build_runtime_manifest(
        release,
        artifact_paths=[(artifact, "python-runtime")],
        license_paths=[license_file],
        version="1.0.0",
    )

    validation = validate_runtime_manifest(release, manifest)

    assert validation.valid is False
    assert "development_secret_residue" in validation.codes


def test_runtime_manifest_ignores_binary_runtime_signature_strings(tmp_path: Path) -> None:
    release, artifact, license_file = _bundle(tmp_path)
    binary = release / "runtime" / "ffmpeg" / "avformat-61.dll"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"MZ\x00authorization: codec metadata\x00")
    manifest = build_runtime_manifest(
        release,
        artifact_paths=[
            (artifact, "python-runtime"),
            (binary, "renderer-runtime"),
        ],
        license_paths=[license_file],
        version="1.0.0",
    )

    assert validate_runtime_manifest(release, manifest).valid is True
