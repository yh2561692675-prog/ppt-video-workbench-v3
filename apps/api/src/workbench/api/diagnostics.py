from __future__ import annotations

from fastapi import APIRouter, HTTPException

from workbench.api.projects import Envelope, envelope
from workbench.diagnostics.center import DiagnosticCenterProtocol
from workbench.diagnostics.models import DiagnosticPackage, DiagnosticReport
from workbench.diagnostics.package import DiagnosticPackager


def create_diagnostics_router(
    center: DiagnosticCenterProtocol,
    packager: DiagnosticPackager,
) -> APIRouter:
    router = APIRouter(prefix="/api/diagnostics")

    @router.post("/run", response_model=Envelope[DiagnosticReport])
    def run_diagnostics() -> Envelope[DiagnosticReport]:
        return envelope(center.run())

    @router.get("/latest", response_model=Envelope[DiagnosticReport])
    def latest_diagnostics() -> Envelope[DiagnosticReport]:
        report = center.latest()
        if report is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "diagnostic_report_not_found",
                    "message": "尚未运行健康检查",
                    "action": "点击开始一键检查",
                },
            )
        return envelope(report)

    @router.post("/package", response_model=Envelope[DiagnosticPackage])
    def create_diagnostic_package() -> Envelope[DiagnosticPackage]:
        report = center.latest() or center.run()
        try:
            package = packager.create(report)
        except (OSError, ValueError) as error:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "diagnostic_package_failed",
                    "message": "诊断报告已生成，但诊断包导出失败",
                    "action": "检查工作区写权限和磁盘空间后重试导出",
                },
            ) from error
        return envelope(package)

    return router
