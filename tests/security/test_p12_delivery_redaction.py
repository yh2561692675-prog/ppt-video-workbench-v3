from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from workbench.business_modules.p12_delivery.models import DeliveryPolicy, MediaProbe
from workbench.business_modules.p12_delivery.policy import verify_package


def test_quality_scan_blocks_secret_and_user_path_without_echoing_secret(tmp_path: Path) -> None:
    secret = "Bearer p12-super-secret-token"
    package = tmp_path / "package.zip"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("logs/run.log", f"{secret}\nC:\\Users\\PrivateName\\source.pptx")

    checks = verify_package(
        package,
        hashlib.sha256(package.read_bytes()).hexdigest(),
        {},
        MediaProbe(
            video_codec="h264",
            audio_codec="aac",
            width=1920,
            height=1080,
            fps=30,
            duration_ms=1000,
            audio_duration_ms=1000,
        ),
        DeliveryPolicy(),
    )
    serialized = " ".join(item.model_dump_json() for item in checks)

    assert next(item for item in checks if item.code == "secret_residue").passed is False
    assert secret not in serialized
    assert "PrivateName" not in serialized
