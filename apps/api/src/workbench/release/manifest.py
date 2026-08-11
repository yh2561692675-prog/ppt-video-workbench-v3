from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReleaseManifestError(ValueError):
    pass


def _default_feature_flags() -> dict[str, Literal["disabled", "internal", "stable_optional"]]:
    return {"presenter_mode": "internal"}


class ReleaseArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relative_path: str
    role: str
    size: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)


class ReleaseLicense(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relative_path: str
    size: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)


class RuntimeManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    manifest_version: Literal[1] = 1
    version: str = Field(min_length=1)
    channel: Literal["stable"] = "stable"
    built_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    artifacts: list[ReleaseArtifact] = Field(default_factory=list)
    licenses: list[ReleaseLicense] = Field(default_factory=list)
    sbom_relative_path: str | None = None
    feature_flags: dict[str, Literal["disabled", "internal", "stable_optional"]] = Field(
        default_factory=_default_feature_flags
    )


class ManifestValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    codes: list[str] = Field(default_factory=list)


_SECRET_PATTERNS = (
    re.compile(rb"api[_-]?key\s*=", re.I),
    re.compile(rb"authorization\s*:", re.I),
    re.compile(rb"secret[_-]?key\s*=", re.I),
    re.compile(rb"sk-[A-Za-z0-9_-]{12,}"),
)

_REQUIRED_RENDERER_RUNTIME_FILES: tuple[tuple[str, str, str], ...] = (
    ("node", "node/node.exe", "node-runtime"),
    ("remotion-cli", "remotion/node_modules/@remotion/cli/remotion-cli.js", "remotion-cli"),
    ("remotion-entry", "remotion/src/index.ts", "remotion-entry"),
    ("ffmpeg", "ffmpeg/ffmpeg.exe", "ffmpeg-runtime"),
    ("ffprobe", "ffmpeg/ffprobe.exe", "ffprobe-runtime"),
)


def build_runtime_manifest(
    release_root: Path,
    *,
    artifact_paths: list[tuple[Path, str]],
    license_paths: list[Path],
    version: str,
    require_licenses: bool = False,
) -> RuntimeManifest:
    artifacts = [
        ReleaseArtifact(
            relative_path=_relative(release_root, path),
            role=role,
            size=path.stat().st_size,
            sha256=_sha256(path),
        )
        for path, role in artifact_paths
    ]
    licenses = [
        ReleaseLicense(
            relative_path=_relative(release_root, path),
            size=path.stat().st_size,
            sha256=_sha256(path),
        )
        for path in license_paths
    ]
    if require_licenses and not licenses:
        raise ReleaseManifestError("许可证清单不能为空")
    return RuntimeManifest(version=version, artifacts=artifacts, licenses=licenses)


def build_release_manifest(
    release_root: Path,
    *,
    api_executable: Path,
    web_index: Path,
    runtime_root: Path,
    license_paths: list[Path],
    version: str,
) -> RuntimeManifest:
    resolved_runtime = runtime_root.resolve()
    missing = [
        name
        for name, relative_path, _ in _REQUIRED_RENDERER_RUNTIME_FILES
        if not (resolved_runtime / relative_path).is_file()
    ]
    if missing:
        raise ReleaseManifestError(f"渲染运行时缺少组件：{', '.join(missing)}")
    runtime_files = sorted(path for path in resolved_runtime.rglob("*") if path.is_file())
    runtime_roles = {
        (resolved_runtime / relative_path).resolve(): role
        for _, relative_path, role in _REQUIRED_RENDERER_RUNTIME_FILES
    }
    artifacts = [
        (api_executable, "api-runtime"),
        (web_index, "web-entry"),
        *[(path, runtime_roles.get(path.resolve(), "renderer-runtime")) for path in runtime_files],
    ]
    return build_runtime_manifest(
        release_root,
        artifact_paths=artifacts,
        license_paths=license_paths,
        version=version,
        require_licenses=True,
    )


def validate_runtime_manifest(
    release_root: Path,
    manifest: RuntimeManifest,
    *,
    require_complete: bool = True,
) -> ManifestValidation:
    root = release_root.resolve()
    codes: set[str] = set()
    if require_complete and not manifest.artifacts:
        codes.add("artifact_inventory_empty")
    if require_complete and not manifest.licenses:
        codes.add("license_inventory_empty")
    seen: set[str] = set()
    for artifact in manifest.artifacts:
        _validate_path(root, artifact.relative_path, codes)
        if artifact.relative_path in seen:
            codes.add("artifact_path_duplicate")
        seen.add(artifact.relative_path)
        path = root / artifact.relative_path
        if not path.is_file():
            codes.add("artifact_missing")
            continue
        if path.stat().st_size != artifact.size:
            codes.add("artifact_size_mismatch")
        if _sha256(path) != artifact.sha256:
            codes.add("artifact_hash_mismatch")
        if _contains_secret(path, artifact.relative_path):
            codes.add("development_secret_residue")
    for license_file in manifest.licenses:
        _validate_path(root, license_file.relative_path, codes)
        path = root / license_file.relative_path
        if not path.is_file():
            codes.add("license_missing")
            continue
        if _sha256(path) != license_file.sha256:
            codes.add("license_hash_mismatch")
    if manifest.sbom_relative_path:
        _validate_path(root, manifest.sbom_relative_path, codes)
        if not (root / manifest.sbom_relative_path).is_file():
            codes.add("sbom_missing")
    return ManifestValidation(valid=not codes, codes=sorted(codes))


def write_runtime_manifest(path: Path, manifest: RuntimeManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(
            manifest.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _relative(root: Path, path: Path) -> str:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved_root not in resolved.parents or not resolved.is_file():
        raise ReleaseManifestError(f"发布文件不在目录内或不存在：{path}")
    return resolved.relative_to(resolved_root).as_posix()


def _validate_path(root: Path, relative_path: str, codes: set[str]) -> None:
    candidate = (root / relative_path).resolve()
    if Path(relative_path).is_absolute() or root not in candidate.parents:
        codes.add("artifact_path_outside_release")


def _contains_secret(path: Path, relative_path: str) -> bool:
    if _is_pinned_renderer_dependency(relative_path):
        return path.name.lower().startswith(".env")
    if path.suffix.lower() in {".dll", ".node", ".pyd", ".so", ".dylib"}:
        return False
    if path.stat().st_size > 5 * 1024 * 1024:
        return False
    try:
        data = path.read_bytes()
    except OSError:
        return False
    return any(pattern.search(data) for pattern in _SECRET_PATTERNS)


def _is_pinned_renderer_dependency(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/").lower()
    return normalized.startswith("runtime/remotion/node_modules/")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
