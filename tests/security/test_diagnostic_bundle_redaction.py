import json
import zipfile
from pathlib import Path

from workbench.diagnostics.models import (
    DiagnosticCategory,
    DiagnosticCheck,
    DiagnosticReport,
    DiagnosticStatus,
)
from workbench.diagnostics.package import DiagnosticPackager


def _report(secret: str, private_path: str) -> DiagnosticReport:
    return DiagnosticReport.build(
        [
            DiagnosticCheck(
                check_id="configuration",
                label="运行配置",
                status=DiagnosticStatus.RED,
                category=DiagnosticCategory.CONFIGURATION,
                code="CONFIGURATION_INVALID",
                summary=f"api_key={secret}",
                impact="配置需要处理",
                remediation="更新密钥引用",
                evidence={
                    "api_key": secret,
                    "authorization": f"Bearer {secret}",
                    "private_path": private_path,
                },
            )
        ]
    )


def test_bundle_never_contains_injected_secrets_or_user_identity(tmp_path: Path) -> None:
    secret = "sk-test-DO-NOT-LEAK"
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJBbGljZSJ9.signature"
    private_path = r"C:\Users\Alice\Documents\private.pptx"
    log = tmp_path / "service.log"
    log.write_text(
        "\n".join(
            [
                f"Authorization: Bearer {secret}",
                "Cookie: session=private-cookie-value",
                f"token={jwt}",
                private_path,
            ]
        ),
        encoding="utf-8",
    )
    package = DiagnosticPackager(
        tmp_path,
        log_paths=(log,),
        username="Alice",
    ).create(_report(secret, private_path))
    archive_path = tmp_path / package.relative_path

    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        extracted = b"\n".join(archive.read(name) for name in names).decode(
            "utf-8", errors="replace"
        )
        manifest = json.loads(archive.read("manifest.json"))

    assert names == {
        "README.txt",
        "diagnostic-report.json",
        "diagnostic-report.md",
        "logs/service.log",
        "manifest.json",
    }
    for forbidden in (secret, jwt, "private-cookie-value", "Alice", private_path):
        assert forbidden not in extracted
    assert "Authorization: Bearer ***" in extracted
    assert "api_key=***" in extracted
    assert "Authorization: *** ***" not in extracted
    assert extracted.count("***") >= 4
    assert "%USERPROFILE%" in extracted
    assert {item["path"] for item in manifest["files"]} == names - {"manifest.json"}
    assert all(len(item["sha256"]) == 64 for item in manifest["files"])
    assert package.sha256 == __import__("hashlib").sha256(archive_path.read_bytes()).hexdigest()


def test_bundle_limits_each_log_to_last_256_kib(tmp_path: Path) -> None:
    log = tmp_path / "large.log"
    log.write_bytes(b"old-secret\n" + b"x" * (300 * 1024))

    package = DiagnosticPackager(tmp_path, log_paths=(log,)).create(DiagnosticReport.build([]))

    with zipfile.ZipFile(tmp_path / package.relative_path) as archive:
        payload = archive.read("logs/large.log")
    assert len(payload) <= 256 * 1024
    assert b"old-secret" not in payload
