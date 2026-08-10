from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from workbench.domain.matching import PageMatch
from workbench.domain.models import AuditEvent
from workbench.services.project_service import ProjectService


class MatchRejected(ValueError):
    pass


class MatchingService:
    def __init__(self, projects: ProjectService) -> None:
        self.projects = projects

    def override(self, project_id: UUID, page_id: UUID, outline_ref: str, reason: str) -> PageMatch:
        manifest = self.projects.get(project_id)
        index = next(
            (
                position
                for position, match in enumerate(manifest.matches)
                if match.page_id == page_id
            ),
            None,
        )
        if index is None:
            raise KeyError(page_id)
        current = manifest.matches[index]
        selected = next(
            (candidate for candidate in current.candidates if candidate.outline_ref == outline_ref),
            None,
        )
        if selected is None:
            raise MatchRejected("人工选择必须来自当前页面的大纲候选")
        changed = current.model_copy(
            update={
                "selected_outline_ref": selected.outline_ref,
                "score": selected.score,
                "needs_confirmation": False,
                "decision_source": "manual",
            }
        )
        matches = list(manifest.matches)
        matches[index] = changed
        now = datetime.now(UTC)
        updated = manifest.model_copy(
            update={
                "matches": matches,
                "audit_log": [
                    *manifest.audit_log,
                    AuditEvent(
                        action="page_match_changed",
                        occurred_at=now,
                        details={
                            "page_id": str(page_id),
                            "previous_outline_ref": current.selected_outline_ref,
                            "outline_ref": outline_ref,
                            "reason": reason,
                        },
                    ),
                ],
            }
        )
        self.projects.save(updated)
        return changed
