from __future__ import annotations

import hashlib
import importlib.metadata
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from workbench.runtime.layout import RuntimeComponentMissingError, RuntimeLayout


class EnvironmentStatus(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    INCOMPATIBLE = "incompatible"
    UNUSABLE = "unusable"
    SKIPPED = "skipped"


class EnvironmentCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: EnvironmentStatus
    version: str | None = None
    path: str | None = None
    code: str
    message: str
    action: str
    blocking: bool


class EnvironmentReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: UUID = Field(default_factory=uuid4)
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    workspace_label: str
    checks: list[EnvironmentCheck] = Field(default_factory=list)
    allowed: bool = False


class DiagnosticPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    report_id: UUID
    relative_path: str
    sha256: str = Field(min_length=64, max_length=64)
    size: int = Field(ge=0)


class _ComponentProbe(NamedTuple):
    version: str | None
    path: str | None


ComponentProbe = Callable[[str], tuple[str | None, str | None]]
DiskProbe = Callable[[Path], tuple[int, int]]
PathProbe = Callable[[Path], bool]
WritableProbe = Callable[[Path], bool]


_COMPONENTS: tuple[tuple[str, tuple[int, int] | None], ...] = (
    ("python", (3, 12)),
    ("node", (18, 0)),
    ("remotion", (4, 0)),
    ("ffmpeg", (6, 0)),
    ("ffprobe", (6, 0)),
    ("libreoffice", (7, 0)),
    ("ocr", (3, 0)),
    ("browser", None),
)
_MIN_FREE_BYTES = 1 * 1024 * 1024 * 1024
_PACKAGED_RUNTIME_COMPONENTS = {"node", "remotion", "ffmpeg", "ffprobe", "browser"}


class EnvironmentDetector:
    def __init__(
        self,
        workspace_root: Path,
        *,
        component_probe: ComponentProbe | None = None,
        disk_probe: DiskProbe | None = None,
        path_probe: PathProbe | None = None,
        writable_probe: WritableProbe | None = None,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.component_probe = component_probe or _default_component_probe
        self.disk_probe = disk_probe or _default_disk_probe
        self.path_probe = path_probe or _default_chinese_path_probe
        self.writable_probe = writable_probe or _default_writable_probe

    def detect_environment(self) -> EnvironmentReport:
        checks = [self._component_check(name, minimum) for name, minimum in _COMPONENTS]
        free, total = self.disk_probe(self.workspace_root)
        checks.append(
            EnvironmentCheck(
                name="disk",
                status=EnvironmentStatus.AVAILABLE
                if free >= _MIN_FREE_BYTES
                else EnvironmentStatus.INCOMPATIBLE,
                version=f"{free} free / {total} total",
                code="disk_ok" if free >= _MIN_FREE_BYTES else "disk_space_low",
                message=(
                    "可用磁盘空间满足发布与渲染需求"
                    if free >= _MIN_FREE_BYTES
                    else "可用磁盘空间不足以安全完成发布或视频导出"
                ),
                action=(
                    "无需处理" if free >= _MIN_FREE_BYTES else "清理可重建缓存或选择空间更大的磁盘"
                ),
                blocking=free < _MIN_FREE_BYTES,
            )
        )
        writable = self.writable_probe(self.workspace_root)
        checks.append(
            EnvironmentCheck(
                name="workspace_permissions",
                status=EnvironmentStatus.AVAILABLE if writable else EnvironmentStatus.UNUSABLE,
                code="workspace_writable" if writable else "workspace_not_writable",
                message="工作区可创建和替换文件" if writable else "工作区没有可用写权限",
                action=("无需处理" if writable else "选择有写权限的项目目录或调整目录权限"),
                blocking=not writable,
            )
        )
        chinese_ok = self.path_probe(self.workspace_root)
        checks.append(
            EnvironmentCheck(
                name="chinese_path",
                status=EnvironmentStatus.AVAILABLE if chinese_ok else EnvironmentStatus.UNUSABLE,
                code="chinese_path_ok" if chinese_ok else "chinese_path_unsupported",
                message="中文目录可创建、读回和删除" if chinese_ok else "中文目录读写校验失败",
                action=("无需处理" if chinese_ok else "将工作区移动到支持 Unicode 路径的本地磁盘"),
                blocking=not chinese_ok,
            )
        )
        return EnvironmentReport(
            workspace_label=self.workspace_root.name or "workspace",
            checks=checks,
            allowed=not any(check.blocking for check in checks),
        )

    def create_diagnostic_package(self, report: EnvironmentReport) -> DiagnosticPackage:
        directory = self.workspace_root / "09_日志" / "诊断"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"环境诊断-{report.report_id}.zip"
        temporary = directory / f".{target.name}.tmp"
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "environment-report.json",
                report.model_dump_json(indent=2) + "\n",
            )
            archive.writestr("environment-report.md", _report_markdown(report))
            archive.writestr(
                "README.txt",
                "该诊断包仅包含脱敏环境检查结果，不包含 API Key、认证头或项目源文件正文。\n",
            )
        os.replace(temporary, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        return DiagnosticPackage(
            report_id=report.report_id,
            relative_path=target.relative_to(self.workspace_root).as_posix(),
            sha256=digest,
            size=target.stat().st_size,
        )

    def _component_check(self, name: str, minimum: tuple[int, int] | None) -> EnvironmentCheck:
        version, path = self.component_probe(name)
        safe_path = Path(path).name if path else None
        if version is None or path is None:
            return EnvironmentCheck(
                name=name,
                status=EnvironmentStatus.MISSING,
                code="component_missing",
                message=f"缺少 {name} 运行组件",
                action=_component_repair_action(name),
                blocking=True,
            )
        if minimum is not None and _version_tuple(version) < minimum:
            return EnvironmentCheck(
                name=name,
                status=EnvironmentStatus.INCOMPATIBLE,
                version=version,
                path=safe_path,
                code="component_version_incompatible",
                message=f"{name} 版本 {version} 低于最低兼容版本",
                action=_component_repair_action(name),
                blocking=True,
            )
        return EnvironmentCheck(
            name=name,
            status=EnvironmentStatus.AVAILABLE,
            version=version,
            path=safe_path,
            code="component_available",
            message=f"{name} 可用",
            action="无需处理",
            blocking=False,
        )


def _default_component_probe(name: str) -> tuple[str | None, str | None]:
    if name == "python":
        return sys.version.split()[0], sys.executable
    if name == "ocr":
        try:
            return importlib.metadata.version("paddleocr"), "paddleocr"
        except importlib.metadata.PackageNotFoundError:
            return None, None
    bundled = _bundled_component_command(name)
    if bundled is not None:
        return _run_version(bundled)
    if os.environ.get("WORKBENCH_RUNTIME_ROOT") and name in _PACKAGED_RUNTIME_COMPONENTS:
        return None, None
    commands = {
        "node": ("node", "--version"),
        "remotion": ("pnpm", "exec remotion --version"),
        "ffmpeg": ("ffmpeg", "-version"),
        "ffprobe": ("ffprobe", "-version"),
        "libreoffice": ("soffice", "--version"),
        "browser": ("msedge", "--version"),
    }
    command = commands.get(name)
    if command is None:
        return None, None
    executable = shutil.which(command[0])
    if executable is None:
        return None, None
    return _run_version([executable, *command[1].split()])


def _bundled_component_command(name: str) -> list[str] | None:
    if name not in _PACKAGED_RUNTIME_COMPONENTS:
        return None
    try:
        runtime = RuntimeLayout.from_environment().require_renderer()
    except RuntimeComponentMissingError:
        return None
    commands = {
        "node": [str(runtime.node_executable), "--version"],
        "remotion": [str(runtime.node_executable), str(runtime.remotion_cli), "--version"],
        "ffmpeg": [str(runtime.ffmpeg_executable), "-version"],
        "ffprobe": [str(runtime.ffprobe_executable), "-version"],
        "browser": (
            [str(runtime.browser_executable), "--version"]
            if runtime.browser_executable is not None
            else None
        ),
    }
    return commands[name]


def _component_repair_action(name: str) -> str:
    if name in _PACKAGED_RUNTIME_COMPONENTS:
        return "重新运行 scripts/prepare-runtime.ps1 并重建安装包，然后再运行环境诊断"
    return f"安装或修复 {name} 后重新运行环境检测"


def _run_version(command: list[str]) -> tuple[str | None, str | None]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    text = result.stdout.strip() or result.stderr.strip()
    version = next(
        (part.lstrip("v") for part in text.split() if part[:1].isdigit()),
        None,
    )
    return version, command[0] if result.returncode == 0 or text else None


def _default_disk_probe(path: Path) -> tuple[int, int]:
    usage = shutil.disk_usage(path)
    return usage.free, usage.total


def _default_writable_probe(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".environment-", delete=True):
            pass
        return True
    except OSError:
        return False


def _default_chinese_path_probe(path: Path) -> bool:
    candidate = path / f"环境检测-{uuid4().hex}"
    try:
        candidate.mkdir(parents=True, exist_ok=False)
        marker = candidate / "读写校验.txt"
        marker.write_text("ok", encoding="utf-8")
        return marker.read_text(encoding="utf-8") == "ok"
    except OSError:
        return False
    finally:
        shutil.rmtree(candidate, ignore_errors=True)


def _version_tuple(version: str) -> tuple[int, int]:
    values: list[int] = []
    for item in version.split(".")[:2]:
        digits = "".join(character for character in item if character.isdigit())
        values.append(int(digits or 0))
    while len(values) < 2:
        values.append(0)
    return values[0], values[1]


def _report_markdown(report: EnvironmentReport) -> str:
    lines = [
        "# 环境诊断报告",
        "",
        f"- 报告 ID：`{report.report_id}`",
        f"- 检查时间：{report.checked_at.isoformat()}",
        f"- 工作区：`{report.workspace_label}`",
        f"- 结论：{'通过' if report.allowed else '阻断'}",
        "",
        "| 组件/检查 | 状态 | 版本 | Code | 修复动作 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for check in report.checks:
        lines.append(
            f"| {check.name} | {check.status.value} | {check.version or '-'} | "
            f"`{check.code}` | {check.action} |"
        )
    return "\n".join(lines) + "\n"
