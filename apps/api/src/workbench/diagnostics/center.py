from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from workbench.diagnostics.models import (
    DiagnosticCategory,
    DiagnosticCheck,
    DiagnosticReport,
    DiagnosticStatus,
)

CheckProbe = Callable[[], DiagnosticCheck]


class DiagnosticCenterProtocol(Protocol):
    def run(self) -> DiagnosticReport: ...

    def latest(self) -> DiagnosticReport | None: ...


CHECK_IDS: tuple[str, ...] = (
    "installation_manifest",
    "python_runtime",
    "ffmpeg_runtime",
    "disk_space",
    "workspace_permissions",
    "loopback_port",
    "database_integrity",
    "configuration",
    "heygen_connectivity",
    "heygen_voices",
    "secret_references",
    "temporary_directory",
    "video_encoder",
)

_CHECK_LABELS = {
    "installation_manifest": "安装清单",
    "python_runtime": "Python 与 VC++ 运行库",
    "ffmpeg_runtime": "FFmpeg 运行时",
    "disk_space": "磁盘空间",
    "workspace_permissions": "工作区权限",
    "loopback_port": "本地端口",
    "database_integrity": "数据库完整性",
    "configuration": "运行配置",
    "heygen_connectivity": "HeyGen 连通性",
    "heygen_voices": "HeyGen 声音列表",
    "secret_references": "密钥引用",
    "temporary_directory": "临时目录",
    "video_encoder": "视频编码能力",
}


class DiagnosticCenter:
    def __init__(
        self,
        workspace_root: Path,
        *,
        probes: Mapping[str, CheckProbe] | None = None,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        if probes is None:
            from workbench.diagnostics.probes import build_default_probes

            probes = build_default_probes(self.workspace_root)
        self._probes = dict(probes)
        self._latest: DiagnosticReport | None = None

    def run(self) -> DiagnosticReport:
        report = DiagnosticReport.build(self._safe_run(check_id) for check_id in CHECK_IDS)
        self._latest = report
        return report

    def latest(self) -> DiagnosticReport | None:
        return self._latest

    def _safe_run(self, check_id: str) -> DiagnosticCheck:
        try:
            probe = self._probes[check_id]
            result = probe()
            if result.check_id != check_id:
                raise ValueError("diagnostic probe returned the wrong check_id")
            return result
        except Exception as error:
            return DiagnosticCheck(
                check_id=check_id,
                label=_CHECK_LABELS[check_id],
                status=DiagnosticStatus.RED,
                category=DiagnosticCategory.INTERNAL,
                code="DIAGNOSTIC_PROBE_FAILED",
                summary="该检查未能完成，其他诊断项已继续执行",
                impact="无法确认此项健康状态",
                remediation="导出诊断包后重新运行；若仍失败，请查看对应检查日志",
                evidence={"exception_type": type(error).__name__},
            )


class UnavailableDiagnosticCenter:
    def __init__(self, exception_type: str) -> None:
        self.exception_type = exception_type
        self._latest: DiagnosticReport | None = None

    def run(self) -> DiagnosticReport:
        report = DiagnosticReport.build(
            DiagnosticCheck(
                check_id=check_id,
                label=_CHECK_LABELS[check_id],
                status=DiagnosticStatus.RED,
                category=DiagnosticCategory.INTERNAL,
                code="DIAGNOSTIC_CENTER_UNAVAILABLE",
                summary="诊断中心暂时不可用，主程序其他功能仍可继续使用",
                impact="当前无法确认此项健康状态",
                remediation="重新启动程序后再次检查，仍失败时导出启动日志",
                evidence={"exception_type": self.exception_type},
            )
            for check_id in CHECK_IDS
        )
        self._latest = report
        return report

    def latest(self) -> DiagnosticReport | None:
        return self._latest
