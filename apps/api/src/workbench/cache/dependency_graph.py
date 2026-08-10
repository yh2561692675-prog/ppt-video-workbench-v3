from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from workbench.domain.models import ProjectManifest


class InvalidationEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    page_id: UUID | None = None
    affected_page_ids: tuple[UUID, ...] = ()
    payload: dict[str, Any] = Field(default_factory=dict)


class InvalidationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preserve: list[str] = Field(default_factory=list)
    rebuild: list[str] = Field(default_factory=list)
    reason: str


class DependencyGraph:
    """Propagate changes through the fixed project-to-video dependency chain."""

    _page_stages = ("narration", "audio", "timeline", "subtitle", "segment")
    _project_stages = ("source", "extraction", "match")

    def invalidate(self, project: ProjectManifest, event: InvalidationEvent) -> InvalidationPlan:
        all_nodes = self._nodes(project)
        rebuild: set[str] = set()
        selected_pages = self._selected_pages(project, event)

        if event.kind == "page_narration_changed":
            rebuild.update(
                self._page_node(page_id, stage)
                for page_id in selected_pages
                for stage in ("narration", "audio", "subtitle", "segment")
            )
        elif event.kind == "page_audio_changed":
            rebuild.update(
                self._page_node(page_id, stage)
                for page_id in selected_pages
                for stage in ("timeline", "subtitle", "segment")
            )
        elif event.kind == "content_changed":
            rebuild.update({"extraction", "match"})
            rebuild.update(
                self._page_node(page_id, stage)
                for page_id in selected_pages
                for stage in self._page_stages
            )
        elif event.kind == "template_changed":
            rebuild.update(
                self._page_node(page_id, "segment") for page_id in self._page_ids(project)
            )
        elif event.kind in {"effect_plan_changed", "effect_plan_regenerated"}:
            rebuild.update(self._page_node(page_id, "segment") for page_id in selected_pages)
        elif event.kind in {"effect_policy_changed", "effect_catalog_upgraded"}:
            rebuild.update(
                self._page_node(page_id, "segment") for page_id in self._page_ids(project)
            )
        elif event.kind == "heygen_voice_changed":
            rebuild.update(
                self._page_node(page_id, stage)
                for page_id in selected_pages
                for stage in ("audio", "timeline", "subtitle", "segment")
            )
        elif event.kind == "runtime_upgraded":
            rebuild.update(self._runtime_nodes(project, event))
        else:
            raise ValueError(f"unsupported invalidation event: {event.kind}")

        if rebuild:
            rebuild.add("final")
        rebuild &= set(all_nodes)
        return InvalidationPlan(
            preserve=[node for node in all_nodes if node not in rebuild],
            rebuild=[node for node in all_nodes if node in rebuild],
            reason=self._reason(event, selected_pages),
        )

    def _nodes(self, project: ProjectManifest) -> list[str]:
        nodes = list(self._project_stages)
        for page_id in self._page_ids(project):
            nodes.extend(self._page_node(page_id, stage) for stage in self._page_stages)
        nodes.append("final")
        return nodes

    def _page_ids(self, project: ProjectManifest) -> list[UUID]:
        return [page.id for page in sorted(project.pages, key=lambda item: item.order)]

    def _selected_pages(self, project: ProjectManifest, event: InvalidationEvent) -> list[UUID]:
        requested = list(event.affected_page_ids)
        if event.page_id is not None:
            requested.append(event.page_id)
        known = set(self._page_ids(project))
        selected = [page_id for page_id in requested if page_id in known]
        return selected or self._page_ids(project)

    def _runtime_nodes(self, project: ProjectManifest, event: InvalidationEvent) -> set[str]:
        incompatible = event.payload.get("incompatible_nodes", [])
        if not isinstance(incompatible, list):
            raise ValueError("runtime incompatible_nodes must be a list")
        page_ids = self._page_ids(project)
        rebuild: set[str] = set()
        for node in incompatible:
            if not isinstance(node, str):
                raise ValueError("runtime incompatible node names must be strings")
            if node in self._project_stages:
                rebuild.add(node)
                if node == "source":
                    rebuild.add("extraction")
                if node in {"source", "extraction"}:
                    rebuild.add("match")
                rebuild.update(
                    self._page_node(page_id, stage)
                    for page_id in page_ids
                    for stage in self._page_stages
                )
                continue
            if node in self._page_stages:
                rebuild.update(self._page_node(page_id, node) for page_id in page_ids)
                if node == "narration":
                    rebuild.update(
                        self._page_node(page_id, stage)
                        for page_id in page_ids
                        for stage in ("audio", "subtitle", "segment")
                    )
                elif node == "audio":
                    rebuild.update(
                        self._page_node(page_id, stage)
                        for page_id in page_ids
                        for stage in ("timeline", "subtitle", "segment")
                    )
                elif node == "timeline":
                    rebuild.update(
                        self._page_node(page_id, stage)
                        for page_id in page_ids
                        for stage in ("subtitle", "segment")
                    )
                elif node == "subtitle":
                    rebuild.update(self._page_node(page_id, "segment") for page_id in page_ids)
                continue
            if node == "final":
                rebuild.add(node)
                continue
            if ":" in node:
                rebuild.add(node)
        return rebuild

    @staticmethod
    def _page_node(page_id: UUID, stage: str) -> str:
        return f"{stage}:{page_id}"

    @staticmethod
    def _reason(event: InvalidationEvent, page_ids: list[UUID]) -> str:
        scope = ",".join(str(page_id) for page_id in page_ids) or "project"
        return f"{event.kind}: {scope}"
