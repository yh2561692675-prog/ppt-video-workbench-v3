from __future__ import annotations

from fastapi import APIRouter

from workbench.api.projects import Envelope, envelope
from workbench.environment.detector import (
    DiagnosticPackage,
    EnvironmentDetector,
    EnvironmentReport,
)


def create_environment_router(detector: EnvironmentDetector) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/environment", response_model=Envelope[EnvironmentReport])
    def environment_report() -> Envelope[EnvironmentReport]:
        return envelope(detector.detect_environment())

    @router.post(
        "/environment/diagnostic-package",
        response_model=Envelope[DiagnosticPackage],
    )
    def diagnostic_package() -> Envelope[DiagnosticPackage]:
        report = detector.detect_environment()
        return envelope(detector.create_diagnostic_package(report))

    return router
