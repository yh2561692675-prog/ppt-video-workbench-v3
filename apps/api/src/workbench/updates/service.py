from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

UpdateStatus = Literal["idle", "staged", "applied", "rolled_back"]
HealthCheck = Callable[[Path], bool]
MigrationHook = Callable[[Path], None]
DiskFreeProbe = Callable[[Path], int]


class UpdateError(RuntimeError):
    def __init__(self, code: str, message: str, action: str) -> None:
        super().__init__(message)
        self.code = code
        self.action = action


class UpdateCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=40)
    channel: str
    notes: str = Field(default="", max_length=2000)
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    package_relative_path: str = Field(min_length=1, max_length=240)


class UpdateState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_version: str
    previous_version: str | None = None
    staged_version: str | None = None
    status: UpdateStatus = "idle"
    updated_at: str | None = None


def hash_update_package(package: Path) -> str:
    """Hash a release directory using stable relative paths and file bytes."""

    if not package.is_dir():
        raise ValueError(f"更新包目录不存在：{package}")
    digest = hashlib.sha256()
    for path in sorted(path for path in package.rglob("*") if path.is_file()):
        relative = path.relative_to(package).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


class UpdateService:
    minimum_free_bytes = 100 * 1024 * 1024

    def __init__(
        self,
        workspace_root: Path,
        *,
        current_version: str = "0.1.0",
        health_check: HealthCheck | None = None,
        migration_hook: MigrationHook | None = None,
        disk_free: DiskFreeProbe | None = None,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.releases_root = self.workspace_root / "releases"
        self.current_dir = self.releases_root / "current"
        self.previous_dir = self.releases_root / "previous"
        self.staged_dir = self.releases_root / "staged"
        self.manifest_path = self.releases_root / "stable-manifest.json"
        self.state_path = self.releases_root / "update-state.json"
        self.default_current_version = current_version
        self.health_check = health_check or (lambda _: True)
        self.migration_hook = migration_hook
        self.disk_free = disk_free or (lambda path: shutil.disk_usage(path).free)

    def state(self) -> UpdateState:
        if self.state_path.is_file():
            return UpdateState.model_validate(
                json.loads(self.state_path.read_text(encoding="utf-8"))
            )
        return UpdateState(current_version=self.default_current_version)

    def check_update(self, channel: str = "stable") -> UpdateCandidate | None:
        if channel != "stable":
            raise UpdateError(
                "stable_channel_required",
                "只允许检查 stable 更新通道",
                "请选择 stable 通道后重试",
            )
        if not self.manifest_path.is_file():
            return None
        try:
            raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            candidate = UpdateCandidate.model_validate(raw)
        except (OSError, ValueError) as error:
            raise UpdateError(
                "update_manifest_invalid",
                "stable 更新清单无法读取或校验",
                "重新生成并校验发布清单",
            ) from error
        if candidate.channel != "stable":
            raise UpdateError(
                "stable_channel_required",
                "更新清单不是 stable 版本",
                "仅选择经过发布校验的 stable 更新",
            )
        if _version_key(candidate.version) <= _version_key(self.state().current_version):
            return None
        return candidate

    def stage_update(self, package: Path) -> UpdateState:
        candidate = self.check_update()
        if candidate is None:
            raise UpdateError(
                "no_update_available",
                "当前没有可暂存的 stable 更新",
                "先检查 stable 更新后重试",
            )
        if self.disk_free(self.workspace_root) < self.minimum_free_bytes:
            raise UpdateError(
                "disk_space_low",
                "磁盘空间不足以安全暂存更新",
                "清理可重建缓存后重试",
            )
        package = package.resolve()
        if not package.is_dir() or not (package / "runtime-manifest.json").is_file():
            raise UpdateError(
                "package_invalid",
                "更新包缺少 runtime-manifest.json",
                "重新下载并校验完整发布包",
            )
        package_hash = hash_update_package(package)
        if package_hash.lower() != candidate.sha256.lower():
            raise UpdateError(
                "package_hash_mismatch",
                "更新包哈希与 stable 清单不一致",
                "删除损坏的下载包并重新获取 stable 版本",
            )
        package_size = sum(path.stat().st_size for path in package.rglob("*") if path.is_file())
        if package_size != candidate.size:
            raise UpdateError(
                "package_size_mismatch",
                "更新包大小与 stable 清单不一致",
                "重新获取并校验 stable 版本",
            )
        self.releases_root.mkdir(parents=True, exist_ok=True)
        temporary = self.releases_root / f".staged-{uuid4().hex}"
        shutil.copytree(package, temporary)
        try:
            if self.staged_dir.exists():
                shutil.rmtree(self.staged_dir)
            temporary.rename(self.staged_dir)
            (self.staged_dir / "release-version.json").write_text(
                json.dumps({"version": candidate.version}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
        current = self.state()
        next_state = UpdateState(
            current_version=current.current_version,
            previous_version=current.previous_version,
            staged_version=candidate.version,
            status="staged",
            updated_at=_now(),
        )
        self._write_state(next_state)
        return next_state

    def stage_update_relative(self, package_relative_path: str) -> UpdateState:
        package = (self.workspace_root / package_relative_path).resolve()
        if not package.is_relative_to(self.workspace_root):
            raise UpdateError(
                "package_path_invalid",
                "更新包路径必须位于工作区内",
                "选择工作区内的更新包目录",
            )
        return self.stage_update(package)

    def apply_update(self) -> UpdateState:
        current = self.state()
        if not self.staged_dir.is_dir() or not current.staged_version:
            raise UpdateError(
                "update_not_staged",
                "没有经过校验的待应用更新",
                "先暂存 stable 更新后再确认应用",
            )
        if self.disk_free(self.workspace_root) < self.minimum_free_bytes:
            raise UpdateError(
                "disk_space_low",
                "磁盘空间不足以安全应用更新",
                "清理可重建缓存后重试",
            )
        backup = self._backup_user_state()
        had_current = self.current_dir.exists()
        try:
            self.releases_root.mkdir(parents=True, exist_ok=True)
            if self.previous_dir.exists():
                shutil.rmtree(self.previous_dir)
            if had_current:
                self.current_dir.rename(self.previous_dir)
            self.staged_dir.rename(self.current_dir)
            if self.migration_hook:
                self.migration_hook(self.current_dir)
            if not self.health_check(self.current_dir):
                raise UpdateError(
                    "health_check_failed",
                    "新版本健康检查失败，已自动回滚",
                    "查看诊断包后重试或继续使用上一版本",
                )
        except Exception as error:
            self._restore_release_after_failure(had_current)
            self._restore_user_state(backup)
            rollback = UpdateState(
                current_version=current.current_version,
                previous_version=current.previous_version,
                staged_version=None,
                status="rolled_back",
                updated_at=_now(),
            )
            self._write_state(rollback)
            if isinstance(error, UpdateError):
                raise error
            raise UpdateError(
                "migration_failed",
                "更新迁移失败，已自动回滚",
                "查看日志后修复迁移问题或继续使用上一版本",
            ) from error
        applied = UpdateState(
            current_version=current.staged_version,
            previous_version=current.current_version if had_current else None,
            staged_version=None,
            status="applied",
            updated_at=_now(),
        )
        self._write_state(applied)
        return applied

    def rollback_update(self) -> UpdateState:
        current = self.state()
        if not self.previous_dir.is_dir() or not current.previous_version:
            raise UpdateError(
                "no_previous_release",
                "没有可回滚的上一版本",
                "保留当前版本或先完成一次 stable 更新",
            )
        temporary = self.releases_root / f".rollback-{uuid4().hex}"
        self.current_dir.rename(temporary)
        try:
            self.previous_dir.rename(self.current_dir)
            temporary.rename(self.previous_dir)
        except Exception:
            if self.current_dir.exists() and not self.previous_dir.exists():
                self.current_dir.rename(self.previous_dir)
            if temporary.exists():
                temporary.rename(self.current_dir)
            raise
        rolled_back = UpdateState(
            current_version=current.previous_version,
            previous_version=current.current_version,
            staged_version=None,
            status="rolled_back",
            updated_at=_now(),
        )
        self._write_state(rolled_back)
        return rolled_back

    def _backup_user_state(self) -> Path:
        backup = self.workspace_root / "update-backups" / uuid4().hex
        backup.mkdir(parents=True, exist_ok=False)
        settings = self.workspace_root / "settings"
        if settings.is_dir():
            shutil.copytree(settings, backup / "settings")
        for name in ("workspace-index.json", "workspace.db"):
            source = self.workspace_root / name
            if source.is_file():
                shutil.copy2(source, backup / name)
        return backup

    def _restore_user_state(self, backup: Path) -> None:
        settings_backup = backup / "settings"
        settings = self.workspace_root / "settings"
        if settings_backup.is_dir():
            if settings.exists():
                shutil.rmtree(settings)
            shutil.copytree(settings_backup, settings)
        for name in ("workspace-index.json", "workspace.db"):
            source = backup / name
            if source.is_file():
                shutil.copy2(source, self.workspace_root / name)

    def _restore_release_after_failure(self, had_current: bool) -> None:
        if self.current_dir.exists():
            shutil.rmtree(self.current_dir)
        if had_current and self.previous_dir.exists():
            self.previous_dir.rename(self.current_dir)

    def _write_state(self, state: UpdateState) -> None:
        self.releases_root.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            state.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.state_path)


def _version_key(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for token in value.replace("-", ".").split("."):
        digits = "".join(character for character in token if character.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def _now() -> str:
    return datetime.now(UTC).isoformat()
