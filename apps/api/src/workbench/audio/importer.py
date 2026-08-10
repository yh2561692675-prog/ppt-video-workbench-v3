from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from workbench.audio.ffmpeg import AudioNormalizationError, normalize_audio
from workbench.domain.audio import AudioImportRecord
from workbench.domain.models import AuditEvent
from workbench.services.project_service import ProjectService

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_SUPPORTED = {".mp3", ".wav"}


class AudioImportError(ValueError):
    pass


class AudioImportService:
    def __init__(self, projects: ProjectService, *, max_bytes: int = 2 * 1024**3) -> None:
        self.projects = projects
        self.max_bytes = max_bytes

    def import_bytes(self, project_id: UUID, name: str, content: bytes) -> AudioImportRecord:
        if not content:
            raise AudioImportError("录音文件为空")
        if len(content) > self.max_bytes:
            raise AudioImportError("录音文件超过大小限制")
        suffix = Path(name).suffix.lower()
        if suffix not in _SUPPORTED:
            raise AudioImportError("仅支持 MP3 或 WAV 录音")
        manifest = self.projects.get(project_id)
        project_dir = self.projects.workspace_root / manifest.project_dir
        original_dir = project_dir / "05_音频" / "原始录音"
        original_dir.mkdir(parents=True, exist_ok=True)
        safe_name = _safe_name(name)
        target = _available_path(original_dir / safe_name)
        target.write_bytes(content)
        try:
            normalized = normalize_audio(target, project_dir / "05_音频" / "规范化")
        except AudioNormalizationError as error:
            target.unlink(missing_ok=True)
            raise AudioImportError(str(error)) from error
        now = datetime.now(UTC)
        record = AudioImportRecord(
            id=uuid4(),
            original_relative_path=target.relative_to(project_dir).as_posix(),
            normalized_relative_path=normalized.wav_path.relative_to(project_dir).as_posix(),
            duration_ms=normalized.duration_ms,
            sample_rate=normalized.sample_rate,
            channels=normalized.channels,
            sha256=normalized.sha256,
            peak_dbfs=normalized.quality.peak_dbfs,
            silence_ratio=normalized.quality.silence_ratio,
            silence_intervals_ms=normalized.quality.silence_intervals_ms,
            needs_confirmation=normalized.quality.needs_confirmation,
            imported_at=now,
        )
        self.projects.save(
            manifest.model_copy(
                update={
                    "audio_import": record,
                    "audit_log": [
                        *manifest.audit_log,
                        AuditEvent(
                            action="local_audio_imported",
                            occurred_at=now,
                            details={
                                "audio_id": str(record.id),
                                "duration_ms": record.duration_ms,
                                "needs_confirmation": record.needs_confirmation,
                                "command": normalized.command_summary,
                            },
                        ),
                    ],
                }
            )
        )
        return record


def _safe_name(name: str) -> str:
    basename = Path(name.replace("\\", "/")).name.strip()
    safe = _INVALID.sub("_", basename).rstrip(". ")
    if not safe:
        raise AudioImportError("录音文件名无有效字符")
    return safe[:180]


def _available_path(path: Path) -> Path:
    if not path.exists():
        return path
    for number in range(2, 10_000):
        candidate = path.with_name(f"{path.stem}_{number}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise AudioImportError("同名录音过多")
