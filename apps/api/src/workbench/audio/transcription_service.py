from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from workbench.audio.models import Transcript
from workbench.audio.transcriber import Transcriber, write_transcript
from workbench.domain.models import AuditEvent
from workbench.services.project_service import ProjectService


class TranscriptionService:
    def __init__(self, projects: ProjectService, transcriber: Transcriber) -> None:
        self.projects = projects
        self.transcriber = transcriber

    def transcribe_project(self, project_id: UUID, *, device: str = "cpu") -> Transcript:
        manifest = self.projects.get(project_id)
        if manifest.audio_import is None:
            raise ValueError("请先导入并规范化本地录音")
        project_dir = self.projects.workspace_root / manifest.project_dir
        audio = (project_dir / manifest.audio_import.normalized_relative_path).resolve()
        if project_dir.resolve() not in audio.parents or not audio.is_file():
            raise ValueError("规范化录音不存在或路径无效")
        checkpoint = project_dir / "05_音频" / "转写检查点.json"
        transcript = self.transcriber.transcribe(audio, device=device, checkpoint=checkpoint)
        artifact = write_transcript(transcript, project_dir)
        now = datetime.now(UTC)
        self.projects.save(
            manifest.model_copy(
                update={
                    "transcript": transcript,
                    "audit_log": [
                        *manifest.audit_log,
                        AuditEvent(
                            action="local_audio_transcribed",
                            occurred_at=now,
                            details={
                                "model": transcript.model,
                                "device": transcript.device,
                                "word_count": len(transcript.words),
                                "artifact": artifact.relative_to(project_dir).as_posix(),
                            },
                        ),
                    ],
                }
            )
        )
        return transcript
