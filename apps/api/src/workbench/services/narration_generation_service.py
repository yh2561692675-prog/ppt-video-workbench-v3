from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from workbench.domain.models import AuditEvent, LlmUsageRecord
from workbench.integrations.llm.client import LlmClient
from workbench.narration.generator import CompletionClient, NarrationGenerator
from workbench.narration.prompt_builder import PageContext
from workbench.narration.repository import NarrationRepository, NarrationRevision
from workbench.services.project_service import ProjectService
from workbench.settings.secret_store import LlmProfileStore


class NarrationGenerationService:
    def __init__(
        self,
        projects: ProjectService,
        profiles: LlmProfileStore,
        client: LlmClient,
        revisions: NarrationRepository,
        completion_factory: Callable[[UUID], CompletionClient] | None = None,
    ) -> None:
        self.projects = projects
        self.profiles = profiles
        self.client = client
        self.revisions = revisions
        self.completion_factory = completion_factory

    def generate(self, project_id: UUID, page_id: UUID, profile_id: UUID) -> NarrationRevision:
        manifest = self.projects.get(project_id)
        page = next((item for item in manifest.pages if item.id == page_id), None)
        if page is None:
            raise KeyError(page_id)
        extraction = next((item for item in manifest.page_extractions if item.id == page_id), None)
        match = next((item for item in manifest.matches if item.page_id == page_id), None)
        selected = None
        if match and match.selected_outline_ref:
            selected = next(
                (
                    candidate
                    for candidate in match.candidates
                    if candidate.outline_ref == match.selected_outline_ref
                ),
                None,
            )
        page_source_ref = extraction.source_ref if extraction else f"page:{page.order}"
        context = PageContext(
            page_id=page.id,
            page_title=page.title,
            page_text=extraction.text if extraction else (match.page_text if match else ""),
            page_source_ref=page_source_ref,
            outline_text=selected.outline_text if selected else "",
            outline_source_ref=selected.outline_ref if selected else None,
            conflicts=match.conflicts if match else [],
            previous_narrations=[
                prior.narration.text
                for prior in sorted(manifest.pages, key=lambda item: item.order)
                if prior.order < page.order and prior.narration is not None
            ],
        )
        credentials = self.profiles.credentials(profile_id)
        completion_client = (
            self.completion_factory(credentials.profile.id)
            if self.completion_factory is not None
            else self.client
        )
        generator = NarrationGenerator(
            completion_client,
            base_url=str(credentials.profile.base_url).rstrip("/"),
            api_key=credentials.api_key,
            model=credentials.profile.model,
        )
        expected_revision_id = page.narration.revision_id if page.narration else None
        draft = generator.generate(context)
        revision = self.revisions.save_revision(
            project_id,
            page_id,
            draft.text,
            "AI草稿",
            expected_revision_id=expected_revision_id,
            source_refs=draft.source_refs,
            insufficiencies=draft.insufficiencies,
            warnings=draft.warnings,
        )
        used = self.profiles.mark_used(profile_id)
        used_at = used.last_used_at or datetime.now(UTC)
        latest = self.projects.get(project_id)
        usage = LlmUsageRecord(
            profile_id=used.id,
            base_url_digest=used.base_url_digest,
            model=used.model,
            used_at=used_at,
        )
        self.projects.save(
            latest.model_copy(
                update={
                    "llm_usage": [*latest.llm_usage, usage],
                    "audit_log": [
                        *latest.audit_log,
                        AuditEvent(
                            action="narration_generated",
                            occurred_at=used_at,
                            details={
                                "page_id": str(page_id),
                                "revision_id": str(revision.id),
                                "profile_id": str(used.id),
                                "base_url_digest": used.base_url_digest,
                                "model": used.model,
                            },
                        ),
                    ],
                }
            )
        )
        return revision
