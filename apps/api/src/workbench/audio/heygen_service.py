from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

from workbench.audio.ffmpeg import AudioNormalizationError, normalize_audio
from workbench.audio.heygen_chunks import (
    CompletedChunk,
    concatenate_normalized_wavs,
    load_completed_chunks,
    save_completed_chunks,
    split_speech_text,
    text_sha256,
)
from workbench.domain.audio import AudioAsset
from workbench.domain.enums import NodeStatus
from workbench.domain.models import AudioRecord, AuditEvent, PageRecord, ProjectManifest
from workbench.integrations.heygen.client import HeyGenClient
from workbench.services.project_service import ProjectService
from workbench.settings.heygen_store import HeyGenProfileStore


class HeyGenRegenerationRequired(RuntimeError):
    pass


class HeyGenRouteSwitchRequired(RuntimeError):
    pass


class HeyGenService:
    def __init__(
        self,
        projects: ProjectService,
        profiles: HeyGenProfileStore,
        client: HeyGenClient,
    ) -> None:
        self.projects = projects
        self.profiles = profiles
        self.client = client

    def synthesize_page(
        self,
        project_id: UUID,
        page_id: UUID,
        revision_id: UUID,
        voice_id: str,
        profile_id: UUID,
        *,
        speed: float = 1,
        replace_existing: bool = False,
    ) -> AudioAsset:
        if not 0.5 <= speed <= 2:
            raise ValueError("语速必须介于 0.5 与 2.0")
        manifest = self.projects.get(project_id)
        page = _page(manifest.pages, page_id)
        narration = page.narration
        if narration is None or narration.revision_id != revision_id:
            raise ValueError("旁白版本不存在或不是当前版本")
        if narration.confirmed_revision_id != revision_id:
            raise ValueError("当前旁白版本尚未确认")
        if any(
            item.id != page_id
            and item.audio is not None
            and item.audio.status is NodeStatus.COMPLETED
            and item.audio.source != "heygen"
            for item in manifest.pages
        ):
            raise HeyGenRouteSwitchRequired("项目已有本地录音，不能付费生成混用的 HeyGen 页面")
        cache_key = hashlib.sha256(f"{revision_id}|{voice_id}|{speed:.3f}|zh".encode()).hexdigest()
        if page.audio and page.audio.status is NodeStatus.COMPLETED:
            if page.audio.source == "heygen" and page.audio.cache_key == cache_key:
                if page.audio.narration_revision_id is None:
                    return self._backfill_legacy_revision(manifest, page, revision_id)
                return _asset(page, cached=True)
            if not replace_existing:
                raise HeyGenRegenerationRequired("成功页面禁止隐式重生，请先明确更换声音")
        credentials = self.profiles.credentials(profile_id)
        project_dir = self.projects.workspace_root / manifest.project_dir
        text_parts = split_speech_text(narration.text)
        if not text_parts:
            raise ValueError("旁白内容为空，无法生成 HeyGen 配音")
        chunk_root = project_dir / "05_音频" / "HeyGen" / "分段" / cache_key
        state_path = project_dir / "05_音频" / "HeyGen" / "分段" / f"{cache_key}.json"
        chunks = (
            {}
            if replace_existing
            else load_completed_chunks(state_path, project_dir, cache_key, text_parts)
        )
        normalized_parts = []
        for index, text_part in enumerate(text_parts, start=1):
            cached_part = chunks.get(index)
            if cached_part is None:
                speech = self.client.generate_speech(
                    credentials.api_key,
                    text=text_part,
                    voice_id=voice_id,
                    speed=speed,
                    language="zh",
                    base_url=str(credentials.profile.base_url),
                )
                downloaded = self.client.download(str(speech.audio_url))
                suffix = ".wav" if "wav" in downloaded.content_type else ".mp3"
                remote = chunk_root / "远端原始" / f"part-{index:03d}{suffix}"
                remote.parent.mkdir(parents=True, exist_ok=True)
                remote.write_bytes(downloaded.content)
                try:
                    normalized = normalize_audio(remote, chunk_root / "规范化")
                except AudioNormalizationError:
                    remote.unlink(missing_ok=True)
                    raise
                cached_part = CompletedChunk(
                    index=index,
                    text_sha256=text_sha256(text_part),
                    normalized_relative_path=normalized.wav_path.relative_to(
                        project_dir
                    ).as_posix(),
                    remote_relative_path=remote.relative_to(project_dir).as_posix(),
                    duration_ms=normalized.duration_ms,
                    request_id=speech.request_id,
                )
                chunks[index] = cached_part
                save_completed_chunks(state_path, cache_key, chunks)
            normalized_parts.append(project_dir / cached_part.normalized_relative_path)
        normalized = concatenate_normalized_wavs(
            normalized_parts,
            project_dir / "05_音频" / "HeyGen" / f"page-{page.order:03d}.normalized.wav",
        )
        relative = normalized.wav_path.relative_to(project_dir).as_posix()
        audio = AudioRecord(
            id=page.audio.id if page.audio else uuid4(),
            status=NodeStatus.COMPLETED,
            source="heygen",
            relative_path=relative,
            duration_ms=normalized.duration_ms,
            cache_key=cache_key,
            narration_revision_id=revision_id,
            voice_id=voice_id,
            remote_request_id=",".join(
                chunks[index].request_id for index in range(1, len(text_parts) + 1)
            ),
        )
        updated_page = page.model_copy(update={"audio": audio})
        now = datetime.now(UTC)
        self.projects.save(
            manifest.model_copy(
                update={
                    "pages": [
                        updated_page if item.id == page_id else item for item in manifest.pages
                    ],
                    "transcript": (
                        None
                        if manifest.transcript is not None
                        and manifest.transcript.model == "heygen_text_alignment"
                        else manifest.transcript
                    ),
                    "subtitle_artifact": None,
                    "audit_log": [
                        *manifest.audit_log,
                        AuditEvent(
                            action=(
                                "heygen_page_replaced"
                                if page.audio is not None
                                else "heygen_page_synthesized"
                            ),
                            occurred_at=now,
                            details={
                                "page_id": str(page_id),
                                "revision_id": str(revision_id),
                                "voice_id": voice_id,
                                "request_id": audio.remote_request_id,
                                "cache_key": cache_key,
                            },
                        ),
                    ],
                }
            )
        )
        self.profiles.mark_used(profile_id)
        return _asset(updated_page, cached=False)

    def _backfill_legacy_revision(
        self, manifest: ProjectManifest, page: PageRecord, revision_id: UUID
    ) -> AudioAsset:
        if page.audio is None:
            raise AssertionError("legacy audio unexpectedly missing")
        updated_page = page.model_copy(
            update={"audio": page.audio.model_copy(update={"narration_revision_id": revision_id})}
        )
        now = datetime.now(UTC)
        self.projects.save(
            manifest.model_copy(
                update={
                    "pages": [
                        updated_page if item.id == page.id else item for item in manifest.pages
                    ],
                    "audit_log": [
                        *manifest.audit_log,
                        AuditEvent(
                            action="heygen_page_revision_backfilled",
                            occurred_at=now,
                            details={"page_id": str(page.id), "revision_id": str(revision_id)},
                        ),
                    ],
                }
            )
        )
        return _asset(updated_page, cached=True)


def _page(pages: list[PageRecord], page_id: UUID) -> PageRecord:
    for page in pages:
        if page.id == page_id:
            return page
    raise KeyError(page_id)


def _asset(page: PageRecord, *, cached: bool) -> AudioAsset:
    if page.audio is None or not page.audio.relative_path or not page.audio.cache_key:
        raise ValueError("页面音频记录不完整")
    return AudioAsset(
        page_id=page.id,
        relative_path=page.audio.relative_path,
        duration_ms=page.audio.duration_ms or 0,
        cache_key=page.audio.cache_key,
        voice_id=page.audio.voice_id or "",
        request_id=page.audio.remote_request_id or "",
        cached=cached,
    )
