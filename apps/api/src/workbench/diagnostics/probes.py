from __future__ import annotations

import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Protocol, cast

from pydantic import JsonValue

from workbench.diagnostics.center import CheckProbe
from workbench.diagnostics.models import (
    DiagnosticCategory,
    DiagnosticCheck,
    DiagnosticStatus,
)
from workbench.runtime.layout import RuntimeComponentMissingError, RuntimeLayout

_GIB = 1024**3


class HeyGenHealthState(StrEnum):
    UNCONFIGURED = "unconfigured"
    AVAILABLE = "available"
    AUTHENTICATION = "authentication"
    NETWORK = "network"
    PROVIDER = "provider"


@dataclass(frozen=True, slots=True)
class HeyGenHealthSnapshot:
    state: HeyGenHealthState
    has_secret_reference: bool
    voice_count: int | None
    error_code: str | None = None


class DiskUsageResult(Protocol):
    free: int


HeyGenProbe = Callable[[], HeyGenHealthSnapshot]
DiskUsageProbe = Callable[[Path], DiskUsageResult]


def _default_disk_usage(path: Path) -> DiskUsageResult:
    return cast(DiskUsageResult, shutil.disk_usage(path))


def build_default_probes(
    workspace_root: Path,
    *,
    heygen_probe: HeyGenProbe | None = None,
) -> Mapping[str, CheckProbe]:
    root = workspace_root.resolve()
    selected_heygen_probe = heygen_probe or _unconfigured_heygen

    @lru_cache(maxsize=1)
    def heygen_snapshot() -> HeyGenHealthSnapshot:
        return selected_heygen_probe()

    return {
        "installation_manifest": lambda: _installation_manifest_check(root),
        "python_runtime": _python_runtime_check,
        "ffmpeg_runtime": _ffmpeg_runtime_check,
        "disk_space": lambda: _disk_space_check(root),
        "workspace_permissions": lambda: _workspace_permissions_check(root),
        "loopback_port": _loopback_port_check,
        "database_integrity": lambda: _database_integrity_check(root),
        "configuration": lambda: _configuration_check(root),
        "heygen_connectivity": lambda: _heygen_connectivity_check(heygen_snapshot()),
        "heygen_voices": lambda: _heygen_voices_check(heygen_snapshot()),
        "secret_references": lambda: _secret_reference_check(heygen_snapshot()),
        "temporary_directory": _temporary_directory_check,
        "video_encoder": _video_encoder_check,
    }


def create_heygen_health_probe(store: object, client: object) -> HeyGenProbe:
    from workbench.integrations.heygen.client import HeyGenIntegrationError

    def probe() -> HeyGenHealthSnapshot:
        profiles = store.list_profiles()  # type: ignore[attr-defined]
        if not profiles:
            return _unconfigured_heygen()
        profile = max(profiles, key=lambda item: item.updated_at)
        try:
            credentials = store.credentials(profile.id)  # type: ignore[attr-defined]
            voices = client.list_voices(  # type: ignore[attr-defined]
                credentials.api_key,
                base_url=str(credentials.profile.base_url),
            )
            return HeyGenHealthSnapshot(
                state=HeyGenHealthState.AVAILABLE,
                has_secret_reference=bool(profile.has_api_key),
                voice_count=len(voices),
            )
        except KeyError:
            return HeyGenHealthSnapshot(
                state=HeyGenHealthState.UNCONFIGURED,
                has_secret_reference=False,
                voice_count=None,
                error_code="heygen_secret_reference_missing",
            )
        except HeyGenIntegrationError as error:
            if error.code == "heygen_authentication_failed":
                state = HeyGenHealthState.AUTHENTICATION
            elif error.code in {"heygen_timeout", "heygen_network_error"}:
                state = HeyGenHealthState.NETWORK
            else:
                state = HeyGenHealthState.PROVIDER
            return HeyGenHealthSnapshot(
                state=state,
                has_secret_reference=bool(profile.has_api_key),
                voice_count=None,
                error_code=error.code,
            )

    return probe


def _installation_manifest_check(_: Path) -> DiagnosticCheck:
    configured = os.environ.get("WORKBENCH_RUNTIME_ROOT")
    if not configured:
        return _check(
            "installation_manifest",
            "安装清单",
            DiagnosticStatus.YELLOW,
            DiagnosticCategory.ENVIRONMENT,
            "INSTALLATION_MANIFEST_DEV_MODE",
            "当前为源码或开发运行模式，未设置安装运行时根目录",
            "无法核对已安装文件清单",
            "正式安装后重新运行检查",
            {"packaged_runtime": False},
        )
    root = Path(configured).resolve()
    candidates = (
        root / "runtime-manifest.json",
        root.parent / "runtime-manifest.json",
    )
    manifest = next((candidate for candidate in candidates if candidate.is_file()), None)
    if not root.is_dir() or manifest is None:
        return _check(
            "installation_manifest",
            "安装清单",
            DiagnosticStatus.RED,
            DiagnosticCategory.ENVIRONMENT,
            "INSTALLATION_MANIFEST_MISSING",
            "已安装运行时或运行清单缺失",
            "渲染组件可能不完整，视频任务可能失败",
            "使用最新安装包覆盖安装后重新检查",
            {"runtime_root_exists": root.is_dir(), "manifest_found": manifest is not None},
        )
    return _check(
        "installation_manifest",
        "安装清单",
        DiagnosticStatus.GREEN,
        DiagnosticCategory.ENVIRONMENT,
        "INSTALLATION_MANIFEST_OK",
        "安装运行时与清单均存在",
        "无影响",
        "无需处理",
        {"manifest": manifest.name},
    )


def _python_runtime_check(
    *,
    platform_name: str | None = None,
    frozen: bool | None = None,
    executable: Path | None = None,
) -> DiagnosticCheck:
    selected_platform = platform_name or os.name
    selected_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else frozen
    if selected_platform != "nt" or not selected_frozen:
        return _check(
            "python_runtime",
            "Python 与 VC++ 运行库",
            DiagnosticStatus.YELLOW,
            DiagnosticCategory.ENVIRONMENT,
            "PYTHON_RUNTIME_DEV_MODE",
            "当前不是冻结的 Windows 发布运行时",
            "无法在此环境核对 python312.dll 和 VC++ DLL",
            "在 Windows 安装版中重新运行检查",
            {"frozen": selected_frozen, "platform": selected_platform},
        )
    executable_root = (executable or Path(sys.executable)).resolve().parent
    internal = executable_root / "_internal"
    python_dll = internal / "python312.dll"
    vc_names = ("vcruntime140.dll", "vcruntime140_1.dll", "msvcp140.dll")
    missing = [name for name in vc_names if not (internal / name).is_file()]
    if not python_dll.is_file() or missing:
        return _check(
            "python_runtime",
            "Python 与 VC++ 运行库",
            DiagnosticStatus.RED,
            DiagnosticCategory.ENVIRONMENT,
            "PYTHON_RUNTIME_INCOMPLETE",
            "Python 或 VC++ 运行库文件不完整",
            "API 进程可能在启动时立即退出",
            "重新安装包含完整 onedir 运行时的版本",
            {"python_dll": python_dll.is_file(), "missing_vc_count": len(missing)},
        )
    return _check(
        "python_runtime",
        "Python 与 VC++ 运行库",
        DiagnosticStatus.GREEN,
        DiagnosticCategory.ENVIRONMENT,
        "PYTHON_RUNTIME_OK",
        "Python 与 VC++ 运行库完整",
        "无影响",
        "无需处理",
        {"python_version": sys.version.split()[0], "vc_runtime_count": len(vc_names)},
    )


def _ffmpeg_runtime_check() -> DiagnosticCheck:
    executable = _ffmpeg_executable()
    if executable is None:
        return _check(
            "ffmpeg_runtime",
            "FFmpeg 运行时",
            DiagnosticStatus.RED,
            DiagnosticCategory.ENVIRONMENT,
            "FFMPEG_MISSING",
            "找不到 FFmpeg 可执行文件",
            "音频处理和视频导出无法运行",
            "重新准备运行时并覆盖安装",
            {"found": False},
        )
    result = _run_command([str(executable), "-version"])
    if result is None or result.returncode != 0:
        return _check(
            "ffmpeg_runtime",
            "FFmpeg 运行时",
            DiagnosticStatus.RED,
            DiagnosticCategory.PROCESSING,
            "FFMPEG_UNUSABLE",
            "FFmpeg 存在但无法正常执行",
            "媒体处理与视频导出可能失败",
            "重新安装运行时或检查安全软件拦截",
            {"executable": executable.name},
        )
    first_line = result.stdout.splitlines()[0] if result.stdout else "ffmpeg"
    return _check(
        "ffmpeg_runtime",
        "FFmpeg 运行时",
        DiagnosticStatus.GREEN,
        DiagnosticCategory.PROCESSING,
        "FFMPEG_OK",
        "FFmpeg 与 FFprobe 运行时可用",
        "无影响",
        "无需处理",
        {"executable": executable.name, "version": first_line[:120]},
    )


def _disk_space_check(
    workspace_root: Path,
    *,
    disk_usage: DiskUsageProbe = _default_disk_usage,
) -> DiagnosticCheck:
    usage = disk_usage(workspace_root)
    free = int(usage.free)
    if free < _GIB:
        status, code, summary = (
            DiagnosticStatus.RED,
            "DISK_SPACE_CRITICAL",
            "可用磁盘空间低于 1 GiB",
        )
    elif free < 5 * _GIB:
        status, code, summary = (
            DiagnosticStatus.YELLOW,
            "DISK_SPACE_LOW",
            "可用磁盘空间低于 5 GiB",
        )
    else:
        status, code, summary = (
            DiagnosticStatus.GREEN,
            "DISK_SPACE_OK",
            "磁盘空间满足当前安全阈值",
        )
    return _check(
        "disk_space",
        "磁盘空间",
        status,
        DiagnosticCategory.STORAGE,
        code,
        summary,
        "空间不足时渲染或打包可能中途失败" if status != DiagnosticStatus.GREEN else "无影响",
        "清理可重建缓存并确保至少保留 5 GiB" if status != DiagnosticStatus.GREEN else "无需处理",
        {"free_bytes": free, "threshold_warning_bytes": 5 * _GIB},
    )


def _workspace_permissions_check(workspace_root: Path) -> DiagnosticCheck:
    workspace_root.mkdir(parents=True, exist_ok=True)
    first = workspace_root / ".diagnostic-write.tmp"
    second = workspace_root / ".diagnostic-replace.tmp"
    try:
        first.write_bytes(b"p02")
        with first.open("ab") as handle:
            handle.flush()
            os.fsync(handle.fileno())
        second.write_bytes(b"replace")
        os.replace(second, first)
        if first.read_bytes() != b"replace":
            raise OSError("atomic replacement verification failed")
    except OSError:
        return _check(
            "workspace_permissions",
            "工作区权限",
            DiagnosticStatus.RED,
            DiagnosticCategory.STORAGE,
            "WORKSPACE_NOT_WRITABLE",
            "工作区无法完成安全写入与原子替换",
            "项目状态和视频产物无法可靠保存",
            "调整目录权限或选择可写本地磁盘",
            {"writable": False},
        )
    finally:
        first.unlink(missing_ok=True)
        second.unlink(missing_ok=True)
    return _check(
        "workspace_permissions",
        "工作区权限",
        DiagnosticStatus.GREEN,
        DiagnosticCategory.STORAGE,
        "WORKSPACE_WRITABLE",
        "工作区支持创建、刷新、替换和删除",
        "无影响",
        "无需处理",
        {"writable": True, "atomic_replace": True},
    )


def _loopback_port_check() -> DiagnosticCheck:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            selected_port = int(listener.getsockname()[1])
    except OSError:
        return _check(
            "loopback_port",
            "本地端口",
            DiagnosticStatus.RED,
            DiagnosticCategory.NETWORK,
            "LOOPBACK_BIND_FAILED",
            "本机回环端口无法绑定",
            "主程序和外围服务可能无法建立本机连接",
            "检查安全软件、端口策略和本机网络服务后重试",
            {"host": "127.0.0.1", "bindable": False},
        )
    return _check(
        "loopback_port",
        "本地端口",
        DiagnosticStatus.GREEN,
        DiagnosticCategory.NETWORK,
        "LOOPBACK_PORT_OK",
        "本机回环端口可正常绑定",
        "无影响",
        "无需处理",
        {"host": "127.0.0.1", "ephemeral_port": selected_port},
    )


def _database_integrity_check(workspace_root: Path) -> DiagnosticCheck:
    candidates = (workspace_root / "workspace.db", workspace_root / "peripheral.db")
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        return _check(
            "database_integrity",
            "数据库完整性",
            DiagnosticStatus.YELLOW,
            DiagnosticCategory.STORAGE,
            "DATABASE_NOT_INITIALIZED",
            "尚未发现已初始化的工作区数据库",
            "新工作区暂时没有可校验数据",
            "创建或打开项目后重新检查",
            {"database_count": 0},
        )
    for path in existing:
        try:
            with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
                result = connection.execute("PRAGMA quick_check").fetchone()
            if result is None or result[0] != "ok":
                raise sqlite3.DatabaseError("quick_check did not return ok")
        except sqlite3.Error:
            return _check(
                "database_integrity",
                "数据库完整性",
                DiagnosticStatus.RED,
                DiagnosticCategory.STORAGE,
                "DATABASE_INTEGRITY_FAILED",
                "数据库完整性检查未通过",
                "项目状态或任务记录可能无法可靠读取",
                "停止新写入并从最近的已验证备份恢复",
                {"database": path.name},
            )
    return _check(
        "database_integrity",
        "数据库完整性",
        DiagnosticStatus.GREEN,
        DiagnosticCategory.STORAGE,
        "DATABASE_INTEGRITY_OK",
        "数据库 quick_check 通过",
        "无影响",
        "无需处理",
        {"database_count": len(existing)},
    )


def _configuration_check(workspace_root: Path) -> DiagnosticCheck:
    configured_workspace = os.environ.get("WORKBENCH_DIAGNOSTIC_ROOT") or os.environ.get(
        "WORKBENCH_WORKSPACE"
    )
    runtime_root = os.environ.get("WORKBENCH_RUNTIME_ROOT")
    workspace_matches = (
        configured_workspace is None or Path(configured_workspace).resolve() == workspace_root
    )
    runtime_exists = runtime_root is None or Path(runtime_root).resolve().is_dir()
    if not workspace_matches or not runtime_exists:
        return _check(
            "configuration",
            "运行配置",
            DiagnosticStatus.RED,
            DiagnosticCategory.CONFIGURATION,
            "CONFIGURATION_INVALID",
            "工作区或运行时配置指向无效位置",
            "任务可能写入错误目录或无法找到运行组件",
            "从安装目录启动并恢复默认工作区配置",
            {"workspace_matches": workspace_matches, "runtime_exists": runtime_exists},
        )
    return _check(
        "configuration",
        "运行配置",
        DiagnosticStatus.GREEN,
        DiagnosticCategory.CONFIGURATION,
        "CONFIGURATION_OK",
        "工作区与运行时配置一致",
        "无影响",
        "无需处理",
        {
            "workspace_configured": configured_workspace is not None,
            "runtime_configured": runtime_root is not None,
        },
    )


def _heygen_connectivity_check(snapshot: HeyGenHealthSnapshot) -> DiagnosticCheck:
    if snapshot.state == HeyGenHealthState.AVAILABLE:
        return _check(
            "heygen_connectivity",
            "HeyGen 连通性",
            DiagnosticStatus.GREEN,
            DiagnosticCategory.PROVIDER,
            "HEYGEN_CONNECTIVITY_OK",
            "HeyGen 服务可访问",
            "无影响",
            "无需处理",
            {"available": True},
        )
    if snapshot.state == HeyGenHealthState.UNCONFIGURED:
        return _check(
            "heygen_connectivity",
            "HeyGen 连通性",
            DiagnosticStatus.YELLOW,
            DiagnosticCategory.CONFIGURATION,
            "HEYGEN_NOT_CONFIGURED",
            "尚未配置 HeyGen",
            "数字人配音路线不可用，本地音频路线不受影响",
            "在设置中添加 HeyGen 配置后重新检查",
            {"configured": False},
        )
    category = {
        HeyGenHealthState.AUTHENTICATION: DiagnosticCategory.AUTHENTICATION,
        HeyGenHealthState.NETWORK: DiagnosticCategory.NETWORK,
        HeyGenHealthState.PROVIDER: DiagnosticCategory.PROVIDER,
    }[snapshot.state]
    code = {
        HeyGenHealthState.AUTHENTICATION: "HEYGEN_AUTHENTICATION_FAILED",
        HeyGenHealthState.NETWORK: "HEYGEN_NETWORK_FAILED",
        HeyGenHealthState.PROVIDER: "HEYGEN_PROVIDER_FAILED",
    }[snapshot.state]
    return _check(
        "heygen_connectivity",
        "HeyGen 连通性",
        DiagnosticStatus.RED,
        category,
        code,
        "HeyGen 健康探测未通过",
        "HeyGen 音频生成暂不可用，本地音频路线不受影响",
        "按错误分类检查凭证、网络或供应商状态后重试",
        {"error_code": snapshot.error_code or "unknown"},
    )


def _heygen_voices_check(snapshot: HeyGenHealthSnapshot) -> DiagnosticCheck:
    if snapshot.state == HeyGenHealthState.AVAILABLE and (snapshot.voice_count or 0) > 0:
        return _check(
            "heygen_voices",
            "HeyGen 声音列表",
            DiagnosticStatus.GREEN,
            DiagnosticCategory.PROVIDER,
            "HEYGEN_VOICES_OK",
            "HeyGen 声音列表可读取",
            "无影响",
            "无需处理",
            {"voice_count": snapshot.voice_count or 0},
        )
    if snapshot.state == HeyGenHealthState.AVAILABLE:
        return _check(
            "heygen_voices",
            "HeyGen 声音列表",
            DiagnosticStatus.RED,
            DiagnosticCategory.PROVIDER,
            "HEYGEN_VOICES_EMPTY",
            "HeyGen 未返回可用声音",
            "无法选择声音生成音频",
            "检查账户声音权限或重新同步资源",
            {"voice_count": 0},
        )
    connectivity = _heygen_connectivity_check(snapshot)
    return _check(
        "heygen_voices",
        "HeyGen 声音列表",
        connectivity.status,
        connectivity.category,
        "HEYGEN_VOICES_SKIPPED",
        "声音列表检查因 HeyGen 当前不可用而跳过",
        "无法确认声音资源可用性",
        connectivity.remediation,
        {"dependency_code": connectivity.code},
    )


def _secret_reference_check(snapshot: HeyGenHealthSnapshot) -> DiagnosticCheck:
    if snapshot.has_secret_reference:
        return _check(
            "secret_references",
            "密钥引用",
            DiagnosticStatus.GREEN,
            DiagnosticCategory.CONFIGURATION,
            "SECRET_REFERENCE_OK",
            "HeyGen 密钥引用存在",
            "无影响",
            "无需处理",
            {"reference_present": True},
        )
    return _check(
        "secret_references",
        "密钥引用",
        DiagnosticStatus.YELLOW,
        DiagnosticCategory.CONFIGURATION,
        "SECRET_REFERENCE_MISSING",
        "尚未保存 HeyGen 密钥引用",
        "HeyGen 路线不可用，本地音频路线不受影响",
        "在设置中保存 HeyGen 凭证",
        {"reference_present": False},
    )


def _temporary_directory_check() -> DiagnosticCheck:
    try:
        with tempfile.NamedTemporaryFile(prefix="p02-diagnostic-", delete=True) as handle:
            handle.write(b"ok")
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        return _check(
            "temporary_directory",
            "临时目录",
            DiagnosticStatus.RED,
            DiagnosticCategory.STORAGE,
            "TEMPORARY_DIRECTORY_UNUSABLE",
            "临时目录无法完成创建、写入或清理",
            "PPT 解析、媒体转换和安装过程可能失败",
            "检查 TEMP/TMP 目录权限和可用空间",
            {"writable": False},
        )
    return _check(
        "temporary_directory",
        "临时目录",
        DiagnosticStatus.GREEN,
        DiagnosticCategory.STORAGE,
        "TEMPORARY_DIRECTORY_OK",
        "临时目录可写且可清理",
        "无影响",
        "无需处理",
        {"writable": True, "cleanup": True},
    )


def _video_encoder_check() -> DiagnosticCheck:
    executable = _ffmpeg_executable()
    if executable is None:
        return _check(
            "video_encoder",
            "视频编码能力",
            DiagnosticStatus.RED,
            DiagnosticCategory.PROCESSING,
            "VIDEO_ENCODER_UNAVAILABLE",
            "无法检查 H.264 编码器",
            "标准 MP4 视频无法可靠导出",
            "重新安装完整 FFmpeg 运行时",
            {"ffmpeg_found": False},
        )
    result = _run_command([str(executable), "-hide_banner", "-encoders"])
    available = (
        result is not None
        and result.returncode == 0
        and any(name in result.stdout for name in ("libx264", "h264_nvenc", "h264_qsv", "h264_amf"))
    )
    return _check(
        "video_encoder",
        "视频编码能力",
        DiagnosticStatus.GREEN if available else DiagnosticStatus.RED,
        DiagnosticCategory.PROCESSING,
        "VIDEO_ENCODER_OK" if available else "VIDEO_ENCODER_MISSING",
        "H.264 编码器可用" if available else "未发现可用 H.264 编码器",
        "无影响" if available else "标准 MP4 视频导出将失败",
        "无需处理" if available else "重新安装带 H.264 编码支持的 FFmpeg",
        {"h264_available": available},
    )


def _ffmpeg_executable() -> Path | None:
    try:
        return RuntimeLayout.from_environment().require_renderer().ffmpeg_executable
    except RuntimeComponentMissingError:
        located = shutil.which("ffmpeg")
        return Path(located).resolve() if located else None


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _unconfigured_heygen() -> HeyGenHealthSnapshot:
    return HeyGenHealthSnapshot(
        state=HeyGenHealthState.UNCONFIGURED,
        has_secret_reference=False,
        voice_count=None,
    )


def _check(
    check_id: str,
    label: str,
    status: DiagnosticStatus,
    category: DiagnosticCategory,
    code: str,
    summary: str,
    impact: str,
    remediation: str,
    evidence: dict[str, JsonValue],
) -> DiagnosticCheck:
    return DiagnosticCheck(
        check_id=check_id,
        label=label,
        status=status,
        category=category,
        code=code,
        summary=summary,
        impact=impact,
        remediation=remediation,
        evidence=evidence,
    )
