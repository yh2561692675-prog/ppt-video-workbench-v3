from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from workbench.domain.confirmation import Confirmation, GateReason, GateResult
from workbench.domain.enums import NodeStatus
from workbench.domain.models import AuditEvent, PageRecord, ProjectManifest
from workbench.services.project_service import ProjectService


class ConfirmationError(RuntimeError):
    def __init__(self, code: str, message: str, action: str) -> None:
        super().__init__(message)
        self.code = code
        self.action = action


class NarrationGateService:
    def __init__(self, projects: ProjectService) -> None:
        self.projects = projects

    def confirm_narration(
        self,
        page_id: UUID,
        revision_id: UUID,
        actor: str,
        project_id: UUID,
        *,
        conflict_resolution: str | None = None,
    ) -> Confirmation:
        return self.confirm_batch(
            project_id,
            [(page_id, revision_id, conflict_resolution)],
            actor,
        )[0]

    def confirm_batch(
        self,
        project_id: UUID,
        items: list[tuple[UUID, UUID, str | None]],
        actor: str,
    ) -> list[Confirmation]:
        manifest = self.projects.get(project_id)
        if len({page_id for page_id, _, _ in items}) != len(items):
            raise ConfirmationError(
                "duplicate_confirmation_page",
                "批量确认中包含重复页面",
                "请移除重复页面后重试",
            )
        validated = [
            _validate_confirmation(manifest, page_id, revision_id, resolution)
            for page_id, revision_id, resolution in items
        ]
        confirmations: list[Confirmation] = []
        events = list(manifest.audit_log)
        for page, revision_id, clean_resolution in validated:
            now = datetime.now(UTC)
            confirmation = Confirmation(
                id=uuid4(),
                page_id=page.id,
                revision_id=revision_id,
                actor=actor.strip(),
                confirmed_at=now,
                conflict_resolution=clean_resolution,
            )
            if page.narration is None:
                raise AssertionError("validated narration unexpectedly missing")
            page.narration = page.narration.model_copy(
                update={
                    "status": NodeStatus.COMPLETED,
                    "confirmed_revision_id": revision_id,
                }
            )
            confirmations.append(confirmation)
            events.append(
                AuditEvent(
                    action="narration_confirmed",
                    occurred_at=now,
                    details={
                        "page_id": str(page.id),
                        "revision_id": str(revision_id),
                        "actor": confirmation.actor,
                        "conflict_resolution": clean_resolution,
                    },
                )
            )
        updated = manifest.model_copy(
            update={
                "narration_confirmations": [*manifest.narration_confirmations, *confirmations],
                "audit_log": events,
            }
        )
        self.projects.save(updated)
        return confirmations

    def can_enter_audio(self, project_id: UUID) -> GateResult:
        manifest = self.projects.get(project_id)
        reasons: list[GateReason] = []
        for page in sorted(manifest.pages, key=lambda item: item.order):
            if page.narration is None:
                reasons.append(
                    _reason(
                        "narration_missing",
                        "本页尚无旁白",
                        page,
                        "请先生成或填写旁白",
                    )
                )
                continue
            if page.narration.confirmed_revision_id != page.narration.revision_id:
                reasons.append(
                    _reason(
                        "narration_unconfirmed",
                        "当前旁白版本尚未确认",
                        page,
                        "请检查并确认当前版本",
                    )
                )
            conflicts = _page_conflicts(manifest, page.id)
            confirmation = _current_confirmation(manifest, page)
            if conflicts and not (confirmation and confirmation.conflict_resolution):
                reasons.append(
                    _reason(
                        "material_conflict_unresolved",
                        "材料冲突尚未留下处理说明",
                        page,
                        "请处理本页材料冲突",
                    )
                )
        return GateResult(allowed=not reasons, reasons=reasons)


def _find_page(manifest: ProjectManifest, page_id: UUID) -> PageRecord:
    for page in manifest.pages:
        if page.id == page_id:
            return page
    raise KeyError(page_id)


def _validate_confirmation(
    manifest: ProjectManifest,
    page_id: UUID,
    revision_id: UUID,
    conflict_resolution: str | None,
) -> tuple[PageRecord, UUID, str | None]:
    page = _find_page(manifest, page_id)
    if page.narration is None:
        raise ConfirmationError("narration_missing", "本页尚无旁白", "请先生成或填写本页旁白")
    if page.narration.revision_id != revision_id:
        raise ConfirmationError(
            "narration_stale_revision",
            "只能确认当前旁白版本",
            "请刷新页面并确认最新版本",
        )
    clean_resolution = (conflict_resolution or "").strip() or None
    if _page_conflicts(manifest, page_id) and clean_resolution is None:
        raise ConfirmationError(
            "material_conflict_unresolved",
            "本页材料冲突尚未处理",
            "请填写冲突处理说明后再确认",
        )
    return page, revision_id, clean_resolution


def _page_conflicts(manifest: ProjectManifest, page_id: UUID) -> list[str]:
    match = next((item for item in manifest.matches if item.page_id == page_id), None)
    return match.conflicts if match else []


def _current_confirmation(manifest: ProjectManifest, page: PageRecord) -> Confirmation | None:
    if page.narration is None:
        return None
    for confirmation in reversed(manifest.narration_confirmations):
        if (
            confirmation.page_id == page.id
            and confirmation.revision_id == page.narration.revision_id
        ):
            return confirmation
    return None


def _reason(code: str, message: str, page: PageRecord, action: str) -> GateReason:
    return GateReason(code=code, message=message, page_id=page.id, action=action)
