from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from .models import (
    MaterialCollection,
    MaterialCollectionCommand,
    MaterialSyncPreview,
)


class MaterialCollectionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class MaterialCollectionService:
    def __init__(
        self,
        root: Path,
        project_dir_resolver: Callable[[UUID], str] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.project_dir_resolver = project_dir_resolver
        self._collections: dict[UUID, list[MaterialCollection]] = {}
        self._lock = RLock()
        self._load()

    def create(self, collection: MaterialCollection) -> MaterialCollection:
        current = collection.with_content_hash()
        with self._lock:
            self._collections.setdefault(current.project_id, []).append(current)
            self._persist(current)
        return current

    def current(self, project_id: UUID) -> MaterialCollection:
        values = self._collections.get(project_id, [])
        if not values:
            raise KeyError(project_id)
        return max(values, key=lambda item: item.revision)

    def revisions(self, project_id: UUID) -> list[MaterialCollection]:
        return sorted(self._collections.get(project_id, []), key=lambda item: item.revision)

    def apply(self, project_id: UUID, command: MaterialCollectionCommand) -> MaterialCollection:
        current = self.current(project_id)
        if command.expected_revision != current.revision:
            raise MaterialCollectionError(
                "material_revision_conflict", "material collection revision does not match"
            )
        data = deepcopy(current.model_dump(mode="python"))
        payload = command.payload
        pages = data["page_sequence"]
        sections = data["sections"]
        if command.kind == "reorder_pages":
            order = [UUID(str(value)) for value in payload.get("page_ids", [])]
            page_by_id = {UUID(str(item["material_page_id"])): item for item in pages}
            if set(order) != set(page_by_id):
                raise MaterialCollectionError(
                    "material_page_order_invalid", "page order must contain every page"
                )
            data["page_sequence"] = [
                page_by_id[page_id] | {"order": index} for index, page_id in enumerate(order)
            ]
        elif command.kind == "reorder_sections":
            order = [UUID(str(value)) for value in payload.get("section_ids", [])]
            section_by_id = {UUID(str(item["section_id"])): item for item in sections}
            if set(order) != set(section_by_id):
                raise MaterialCollectionError(
                    "material_section_order_invalid", "section order must contain every section"
                )
            data["sections"] = [
                section_by_id[section_id] | {"order": index}
                for index, section_id in enumerate(order)
            ]
        elif command.kind == "merge_sections":
            source_ids = [UUID(str(value)) for value in payload.get("section_ids", [])]
            if len(source_ids) < 2:
                raise MaterialCollectionError(
                    "material_merge_invalid", "at least two sections are required"
                )
            selected = [item for item in sections if UUID(str(item["section_id"])) in source_ids]
            if len(selected) != len(source_ids):
                raise MaterialCollectionError("material_section_not_found", "section not found")
            merged = selected[0] | {
                "title": str(payload.get("title") or selected[0]["title"]),
                "page_ids": [page_id for item in selected for page_id in item["page_ids"]],
            }
            data["sections"] = [
                item for item in sections if UUID(str(item["section_id"])) not in source_ids
            ] + [merged]
        elif command.kind == "split_section":
            section_id = UUID(str(payload["section_id"]))
            cut = int(payload["page_index"])
            section = next(
                (item for item in sections if UUID(str(item["section_id"])) == section_id), None
            )
            if section is None or cut <= 0 or cut >= len(section["page_ids"]):
                raise MaterialCollectionError(
                    "material_split_invalid", "section split point is invalid"
                )
            first, second = section["page_ids"][:cut], section["page_ids"][cut:]
            section["page_ids"] = first
            data["sections"] = sections + [
                {
                    "section_id": uuid4(),
                    "order": section["order"] + 1,
                    "title": str(payload.get("title") or "拆分章节"),
                    "enabled": True,
                    "page_ids": second,
                }
            ]
        elif command.kind in {"replace_page", "disable_page"}:
            page_id = UUID(str(payload["material_page_id"]))
            page = next(
                (item for item in pages if UUID(str(item["material_page_id"])) == page_id), None
            )
            if page is None:
                raise MaterialCollectionError("material_page_not_found", "page not found")
            if command.kind == "disable_page":
                page["enabled"] = False
            else:
                page.update(
                    {
                        "source_ref": str(payload["source_ref"]),
                        "source_asset_id": payload.get("source_asset_id"),
                        "title": str(payload.get("title") or page["title"]),
                        "visual_hash": payload.get("visual_hash"),
                        "text_hash": payload.get("text_hash"),
                    }
                )
        else:
            raise MaterialCollectionError(
                "material_command_unknown", "unknown material collection command"
            )
        next_value = (
            MaterialCollection.model_validate(data)
            .model_copy(update={"revision": current.revision + 1})
            .with_content_hash()
        )
        with self._lock:
            self._collections.setdefault(project_id, []).append(next_value)
            self._persist(next_value)
        return next_value

    def sync_preview(
        self, project_id: UUID, timeline_revision: int | None = None
    ) -> MaterialSyncPreview:
        current = self.current(project_id)
        pages = current.page_sequence
        return MaterialSyncPreview(
            collection_revision=current.revision,
            timeline_revision=timeline_revision,
            added_page_ids=[page.material_page_id for page in pages if page.enabled],
            disabled_page_ids=[page.material_page_id for page in pages if not page.enabled],
            warnings=["时间线同步必须由用户确认后提交"] if pages else [],
        )

    def _project_root(self, project_id: UUID) -> Path:
        relative = (
            self.project_dir_resolver(project_id) if self.project_dir_resolver else str(project_id)
        )
        return (self.root / relative).resolve()

    def _path(self, project_id: UUID, revision: int) -> Path:
        return (
            self._project_root(project_id)
            / "01_材料集合"
            / "collections"
            / f"revision-{revision}.json"
        )

    def _persist(self, collection: MaterialCollection) -> None:
        target = self._path(collection.project_id, collection.revision)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(collection.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)

    def _load(self) -> None:
        for path in self.root.glob("*/01_材料集合/collections/revision-*.json"):
            try:
                value = MaterialCollection.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            self._collections.setdefault(value.project_id, []).append(value)
