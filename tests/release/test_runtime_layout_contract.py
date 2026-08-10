from __future__ import annotations

from pathlib import Path

import pytest


def _release_with_renderer_runtime(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    release = tmp_path / "release"
    api = release / "api" / "workbench.exe"
    web = release / "web" / "index.html"
    license_file = release / "licenses" / "THIRD-PARTY-NOTICES.txt"
    for path in (api, web, license_file):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(path.name, encoding="utf-8")
    runtime = release / "runtime"
    for relative_path in (
        "node/node.exe",
        "remotion/node_modules/@remotion/cli/remotion-cli.js",
        "remotion/src/index.ts",
        "ffmpeg/ffmpeg.exe",
        "ffmpeg/ffprobe.exe",
    ):
        path = runtime / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative_path, encoding="utf-8")
    return release, api, web, runtime, license_file


def test_release_manifest_records_required_renderer_assets(tmp_path: Path) -> None:
    from workbench.release.manifest import build_release_manifest

    release, api, web, runtime, license_file = _release_with_renderer_runtime(tmp_path)
    manifest = build_release_manifest(
        release,
        api_executable=api,
        web_index=web,
        runtime_root=runtime,
        license_paths=[license_file],
        version="1.0.0",
    )

    paths = {artifact.relative_path for artifact in manifest.artifacts}
    assert {
        "runtime/node/node.exe",
        "runtime/remotion/node_modules/@remotion/cli/remotion-cli.js",
        "runtime/remotion/src/index.ts",
        "runtime/ffmpeg/ffmpeg.exe",
        "runtime/ffmpeg/ffprobe.exe",
    } <= paths


def test_release_manifest_rejects_missing_remotion_cli(tmp_path: Path) -> None:
    from workbench.release.manifest import ReleaseManifestError, build_release_manifest

    release, api, web, runtime, license_file = _release_with_renderer_runtime(tmp_path)
    (runtime / "remotion/node_modules/@remotion/cli/remotion-cli.js").unlink()

    with pytest.raises(ReleaseManifestError, match="remotion-cli"):
        build_release_manifest(
            release,
            api_executable=api,
            web_index=web,
            runtime_root=runtime,
            license_paths=[license_file],
            version="1.0.0",
        )
