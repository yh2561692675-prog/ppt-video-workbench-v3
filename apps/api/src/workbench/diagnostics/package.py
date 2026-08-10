from __future__ import annotations

import hashlib
import json
import os
import zipfile
from collections.abc import Iterable
from pathlib import Path

from workbench.diagnostics.models import DiagnosticPackage, DiagnosticReport
from workbench.diagnostics.redaction import redact_text, redact_value

_LOG_SUFFIXES = {".log", ".txt", ".json", ".ndjson"}
_PER_LOG_LIMIT = 256 * 1024
_TOTAL_LOG_LIMIT = 2 * 1024 * 1024


class DiagnosticPackager:
    def __init__(
        self,
        workspace_root: Path,
        *,
        log_paths: Iterable[Path] = (),
        username: str | None = None,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.log_paths = tuple(Path(path) for path in log_paths)
        self.username = username

    def create(self, report: DiagnosticReport) -> DiagnosticPackage:
        directory = self.workspace_root / "diagnostics"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"P02-diagnostic-{report.report_id}.zip"
        temporary = target.with_suffix(".zip.tmp")
        entries = self._entries(report)
        manifest = {
            "schema_version": "1.0",
            "report_id": str(report.report_id),
            "files": [
                {
                    "path": name,
                    "size_bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
                for name, payload in sorted(entries.items())
            ],
        }
        entries["manifest.json"] = _json_bytes(manifest)
        try:
            with zipfile.ZipFile(
                temporary,
                "w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as archive:
                for name, payload in sorted(entries.items()):
                    archive.writestr(name, payload)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        payload = target.read_bytes()
        return DiagnosticPackage(
            report_id=report.report_id,
            relative_path=target.relative_to(self.workspace_root).as_posix(),
            sha256=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
        )

    def _entries(self, report: DiagnosticReport) -> dict[str, bytes]:
        payload = redact_value(
            report.model_dump(mode="json"),
            workspace_root=self.workspace_root,
            username=self.username,
        )
        entries = {
            "diagnostic-report.json": _json_bytes(payload),
            "diagnostic-report.md": _markdown(payload).encode("utf-8"),
            "README.txt": (
                "PPT Video Workbench P02 诊断包。\n"
                "仅包含脱敏的环境证据和限长日志摘录；不包含项目正文、媒体或密钥明文。\n"
            ).encode(),
        }
        budget = _TOTAL_LOG_LIMIT
        used_names: set[str] = set()
        for path in self.log_paths:
            if budget <= 0 or not path.is_file() or path.suffix.lower() not in _LOG_SUFFIXES:
                continue
            size = min(_PER_LOG_LIMIT, budget, path.stat().st_size)
            raw = _read_tail(path, size)
            sanitized = redact_text(
                raw.decode("utf-8", errors="replace"),
                workspace_root=self.workspace_root,
                username=self.username,
            ).encode("utf-8")
            name = _unique_name(path.name, used_names)
            used_names.add(name)
            entries[f"logs/{name}"] = sanitized
            budget -= len(raw)
        return entries


def _read_tail(path: Path, size: int) -> bytes:
    if size <= 0:
        return b""
    with path.open("rb") as handle:
        handle.seek(-size, os.SEEK_END)
        return handle.read(size)


def _unique_name(name: str, used: set[str]) -> str:
    if name not in used:
        return name
    source = Path(name)
    index = 2
    while True:
        candidate = f"{source.stem}-{index}{source.suffix}"
        if candidate not in used:
            return candidate
        index += 1


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _markdown(payload: object) -> str:
    if not isinstance(payload, dict):
        raise TypeError("diagnostic report payload must be an object")
    lines = [
        "# PPT Video Workbench 健康诊断",
        "",
        f"- 总体状态：{payload.get('overall_status', 'unknown')}",
        f"- 检查时间：{payload.get('checked_at', 'unknown')}",
        "",
    ]
    checks = payload.get("checks")
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict):
                continue
            lines.extend(
                [
                    f"## {check.get('label', check.get('check_id', '检查项'))}",
                    "",
                    f"- 状态：{check.get('status', 'unknown')}",
                    f"- 分类：{check.get('category', 'unknown')}",
                    f"- 代码：{check.get('code', 'unknown')}",
                    f"- 说明：{check.get('summary', '')}",
                    f"- 影响：{check.get('impact', '')}",
                    f"- 建议：{check.get('remediation', '')}",
                    "",
                ]
            )
    return "\n".join(lines)
