from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from uuid import UUID

from workbench.services.project_service import ProjectService

from .models import (
    ChapterMarker,
    ContinuityPlan,
    ContinuityPlanCommand,
    OverlayPlacement,
    TransitionSpec,
)


class ContinuityError(ValueError):
    pass


class ContinuityConflict(ContinuityError):
    pass


class ContinuityService:
    def __init__(
        self,
        workspace_root: Path,
        project_dir_resolver: Callable[[UUID], str],
        projects: ProjectService | None = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.project_dir_resolver = project_dir_resolver
        self.projects = projects
        self._plans: dict[UUID, ContinuityPlan] = {}
        self._applied: dict[UUID, dict[UUID, ContinuityPlan]] = {}

    def create(self, project_id: UUID, *, duration_ms: int = 0) -> ContinuityPlan:
        existing = self._plans.get(project_id)
        if existing is not None:
            return existing
        plan = ContinuityPlan(
            project_id=project_id,
            duration_ms=duration_ms,
            content_hash="",
        )
        if self.projects is not None:
            project = self.projects.get(project_id)
            pages = sorted(project.pages, key=lambda page: page.order)
            if pages:
                for left, right in zip(pages, pages[1:], strict=False):
                    plan.transitions.append(
                        TransitionSpec(from_page_id=left.id, to_page_id=right.id)
                    )
                plan.duration_ms = max(
                    (page.timeline.end_ms for page in pages if page.timeline is not None),
                    default=duration_ms,
                )
        plan = self._with_hash(plan)
        self._plans[project_id] = plan
        self._persist(project_id, plan)
        return plan

    def get(self, project_id: UUID) -> ContinuityPlan:
        cached = self._plans.get(project_id)
        if cached is not None:
            return cached
        loaded = self._load_latest(project_id)
        if loaded is not None:
            self._plans[project_id] = loaded
            return loaded
        return self.create(project_id)

    def revisions(self, project_id: UUID) -> list[ContinuityPlan]:
        folder = self._folder(project_id)
        revisions = sorted(folder.glob("revision-*.json"), key=lambda item: item.name)
        return [
            ContinuityPlan.model_validate_json(path.read_text(encoding="utf-8"))
            for path in revisions
        ] or [self.get(project_id)]

    def apply(self, project_id: UUID, command: ContinuityPlanCommand) -> ContinuityPlan:
        current = self.get(project_id)
        applied = self._applied.setdefault(project_id, {})
        previous = applied.get(command.command_id)
        if previous is not None:
            return previous
        if command.expected_revision != current.revision:
            raise ContinuityConflict(
                f"expected revision {command.expected_revision}, current is {current.revision}"
            )
        candidate = deepcopy(current)
        self._apply_command(candidate, command)
        candidate.revision += 1
        candidate = self._with_hash(candidate)
        self._plans[project_id] = candidate
        applied[command.command_id] = candidate
        self._persist(project_id, candidate)
        return candidate

    def _apply_command(self, plan: ContinuityPlan, command: ContinuityPlanCommand) -> None:
        payload = command.payload
        if command.kind == "upsert_transition":
            transition = TransitionSpec.model_validate(payload.get("transition", payload))
            plan.transitions = [item for item in plan.transitions if item.id != transition.id]
            plan.transitions.append(transition)
            return
        if command.kind == "remove_transition":
            transition_id = str(payload.get("transition_id", ""))
            plan.transitions = [item for item in plan.transitions if str(item.id) != transition_id]
            return
        if command.kind == "upsert_overlay":
            overlay = OverlayPlacement.model_validate(payload.get("overlay", payload))
            if plan.duration_ms > 0 and overlay.start_ms + overlay.duration_ms > plan.duration_ms:
                raise ContinuityError("overlay exceeds continuity plan duration")
            plan.overlays = [item for item in plan.overlays if item.id != overlay.id]
            plan.overlays.append(overlay)
            return
        if command.kind == "remove_overlay":
            overlay_id = str(payload.get("overlay_id", ""))
            plan.overlays = [item for item in plan.overlays if str(item.id) != overlay_id]
            return
        if command.kind == "upsert_chapter":
            chapter = ChapterMarker.model_validate(payload.get("chapter", payload))
            if plan.duration_ms > 0 and chapter.end_ms > plan.duration_ms:
                raise ContinuityError("chapter exceeds continuity plan duration")
            plan.chapters = [item for item in plan.chapters if item.id != chapter.id]
            plan.chapters.append(chapter)
            plan.chapters.sort(key=lambda item: item.start_ms)
            return
        if command.kind == "remove_chapter":
            chapter_id = str(payload.get("chapter_id", ""))
            plan.chapters = [item for item in plan.chapters if str(item.id) != chapter_id]
            return
        raise ContinuityError(f"unsupported continuity command: {command.kind}")

    def _folder(self, project_id: UUID) -> Path:
        root = self._project_root(project_id)
        folder = root / "07_连续镜头"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _project_root(self, project_id: UUID) -> Path:
        root = (self.workspace_root / self.project_dir_resolver(project_id)).resolve()
        workspace = self.workspace_root.resolve()
        if root != workspace and workspace not in root.parents:
            raise ContinuityError("project path escapes workspace root")
        return root

    def _load_latest(self, project_id: UUID) -> ContinuityPlan | None:
        folder = self._folder(project_id)
        revisions = sorted(folder.glob("revision-*.json"), key=lambda item: item.name)
        if not revisions:
            return None
        return ContinuityPlan.model_validate_json(revisions[-1].read_text(encoding="utf-8"))

    def _persist(self, project_id: UUID, plan: ContinuityPlan) -> None:
        folder = self._folder(project_id)
        content = (plan.model_dump_json(indent=2) + "\n").encode("utf-8")
        _atomic_write(folder / f"revision-{plan.revision:08d}.json", content)
        _atomic_write(folder / "current.json", content)

    @staticmethod
    def _with_hash(plan: ContinuityPlan) -> ContinuityPlan:
        payload = plan.model_dump(mode="json", exclude={"content_hash"})
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        return plan.model_copy(update={"content_hash": digest})


def _atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)
