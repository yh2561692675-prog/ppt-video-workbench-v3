from __future__ import annotations

from uuid import UUID

from workbench.audio.service import AudioService
from workbench.domain.confirmation import GateReason, GateResult
from workbench.domain.models import PageRecord, ProjectManifest


class AudioGateService:
    def __init__(self, audio: AudioService) -> None:
        self.audio = audio

    def can_enter_subtitles(self, project: ProjectManifest) -> GateResult:
        if not project.pages:
            return GateResult(
                allowed=False,
                reasons=[
                    _reason(
                        "project_pages_missing",
                        "项目尚无可配音页面",
                        project.id,
                        "请先完成课件解析并生成页面",
                    )
                ],
            )
        page_audio, reasons = self.audio.inspect_page_audio(project)
        reasons.extend(_narration_reasons(project.pages))
        sources = {item.source for item in page_audio}
        if len(sources) > 1:
            reasons.extend(
                _reason(
                    "audio_route_mixed",
                    "同一项目不能混用本地录音和 HeyGen 音频",
                    page.id,
                    "请保留一种音频路线并重做冲突页面",
                )
                for page in project.pages
                if page.audio is not None
            )
        if sources == {"local"}:
            reasons.extend(_local_route_reasons(project))
        if sources == {"heygen"}:
            reasons.extend(_heygen_route_reasons(project.pages))
        return GateResult(allowed=not reasons, reasons=_deduplicate(reasons))


def _narration_reasons(pages: list[PageRecord]) -> list[GateReason]:
    return [
        _reason(
            "page_audio_stale",
            "当前旁白版本未确认，已有音频不能继续使用",
            page.id,
            "请确认当前旁白后重新生成本页音频",
        )
        for page in pages
        if page.narration is None
        or page.narration.confirmed_revision_id != page.narration.revision_id
    ]


def _local_route_reasons(project: ProjectManifest) -> list[GateReason]:
    reasons: list[GateReason] = []
    page_ids = {page.id for page in project.pages}
    timeline_ids = (
        {segment.page_id for segment in project.audio_timeline.segments}
        if project.audio_timeline is not None
        else set()
    )
    if project.audio_timeline is None or timeline_ids != page_ids:
        reasons.extend(
            _reason(
                "audio_timeline_incomplete",
                "本地录音尚未形成覆盖全部页面的时间轴",
                page.id,
                "请重新自动分页并检查边界",
            )
            for page in project.pages
        )
    for difference in project.audio_differences:
        if difference.status == "resolved":
            continue
        code = (
            "audio_difference_severe"
            if difference.kind != "uncertain"
            else "audio_difference_unconfirmed"
        )
        message = (
            "本页存在严重旁白错位或漏读差异"
            if code == "audio_difference_severe"
            else "本页存在未由人工确认的普通录音差异"
        )
        action = (
            "请重新录制或修改旁白后重新对齐"
            if code.endswith("severe")
            else "请人工确认该差异处理方式"
        )
        reasons.append(_reason(code, message, difference.page_id, action))
    return reasons


def _heygen_route_reasons(pages: list[PageRecord]) -> list[GateReason]:
    voices = {page.audio.voice_id for page in pages if page.audio is not None}
    if len(voices) <= 1 and None not in voices:
        return []
    return [
        _reason(
            "heygen_voice_mixed",
            "HeyGen 页面使用了不同声音或缺少声音标识",
            page.id,
            "请统一声音后仅重新生成受影响页面",
        )
        for page in pages
        if page.audio is not None
    ]


def _reason(code: str, message: str, page_id: UUID, action: str) -> GateReason:
    return GateReason(code=code, message=message, page_id=page_id, action=action)


def _deduplicate(reasons: list[GateReason]) -> list[GateReason]:
    result: list[GateReason] = []
    seen: set[tuple[str, UUID]] = set()
    for reason in reasons:
        key = (reason.code, reason.page_id)
        if key not in seen:
            result.append(reason)
            seen.add(key)
    return result
