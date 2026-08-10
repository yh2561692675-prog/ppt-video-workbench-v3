from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from workbench.domain.confirmation import GateReason
from workbench.domain.enums import NodeStatus
from workbench.domain.models import PageRecord, ProjectManifest


class PageAudio(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    page_id: UUID
    path: str
    duration_ms: int = Field(gt=0)
    source: Literal["local", "heygen"]
    cache_key: str


class AudioResolutionError(ValueError):
    def __init__(self, reasons: list[GateReason]) -> None:
        super().__init__("页面音频尚未满足统一契约")
        self.reasons = reasons


class AudioService:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root.resolve()

    def resolve_page_audio(self, project: ProjectManifest) -> list[PageAudio]:
        page_audio, reasons = self.inspect_page_audio(project)
        if reasons:
            raise AudioResolutionError(reasons)
        return page_audio

    def inspect_page_audio(
        self, project: ProjectManifest
    ) -> tuple[list[PageAudio], list[GateReason]]:
        project_root = (self.workspace_root / project.project_dir).resolve()
        audio: list[PageAudio] = []
        reasons: list[GateReason] = []
        used_paths: dict[Path, UUID] = {}
        used_cache_keys: dict[str, UUID] = {}
        for page in sorted(project.pages, key=lambda item: item.order):
            item = _page_audio(page, project_root)
            if isinstance(item, GateReason):
                reasons.append(item)
                continue
            target = (project_root / item.path).resolve()
            if target in used_paths:
                reasons.append(
                    _reason(
                        "page_audio_reused",
                        "该页面复用了其他页面的音频文件",
                        page,
                        "请仅重新生成或导入本页音频",
                    )
                )
            else:
                used_paths[target] = page.id
            if item.cache_key in used_cache_keys:
                reasons.append(
                    _reason(
                        "page_audio_reused",
                        "该页面复用了其他页面的音频缓存",
                        page,
                        "请仅重新生成或导入本页音频",
                    )
                )
            else:
                used_cache_keys[item.cache_key] = page.id
            audio.append(item)
        return audio, reasons


def _page_audio(page: PageRecord, project_root: Path) -> PageAudio | GateReason:
    raw = page.audio
    if raw is None or raw.status is not NodeStatus.COMPLETED:
        return _reason("page_audio_missing", "本页尚无已完成的音频", page, "请完成本页配音")
    if not raw.relative_path:
        return _reason("page_audio_missing", "本页音频路径缺失", page, "请重新生成本页音频")
    if raw.duration_ms is None or raw.duration_ms <= 0:
        return _reason("page_audio_invalid", "本页音频时长无效", page, "请重新生成本页音频")
    if not raw.cache_key:
        return _reason(
            "page_audio_cache_missing", "本页音频缺少版本缓存键", page, "请重新生成本页音频"
        )
    narration = page.narration
    if narration is None or raw.narration_revision_id != narration.revision_id:
        return _reason(
            "page_audio_stale",
            "本页音频不对应当前旁白版本",
            page,
            "请使用当前已确认旁白重新生成本页音频",
        )
    target = (project_root / raw.relative_path).resolve()
    if project_root not in target.parents or not target.is_file() or target.stat().st_size == 0:
        return _reason(
            "page_audio_invalid", "本页音频文件不存在、为空或路径无效", page, "请重新生成本页音频"
        )
    return PageAudio(
        page_id=page.id,
        path=raw.relative_path,
        duration_ms=raw.duration_ms,
        source=raw.source,
        cache_key=raw.cache_key,
    )


def _reason(code: str, message: str, page: PageRecord, action: str) -> GateReason:
    return GateReason(code=code, message=message, page_id=page.id, action=action)
