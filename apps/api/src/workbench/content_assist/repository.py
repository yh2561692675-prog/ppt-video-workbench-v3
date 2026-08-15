"""Atomic persistence for reviewable content-assist candidates."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock
from uuid import UUID

from .models import ContentAssistCandidateV1


class ContentAssistRepositoryError(RuntimeError):
    pass


class ContentAssistRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.path = root / "candidates.json"
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._items: dict[str, ContentAssistCandidateV1] = {}
        self._load()

    def save(self, candidate: ContentAssistCandidateV1) -> ContentAssistCandidateV1:
        with self._lock:
            if str(candidate.candidate_id) in self._items:
                raise ContentAssistRepositoryError("candidate_exists")
            self._items[str(candidate.candidate_id)] = candidate
            self._save()
            return candidate

    def get(self, candidate_id: UUID) -> ContentAssistCandidateV1:
        try:
            return self._items[str(candidate_id)]
        except KeyError as error:
            raise ContentAssistRepositoryError("candidate_not_found") from error

    def update(self, candidate: ContentAssistCandidateV1) -> ContentAssistCandidateV1:
        with self._lock:
            if str(candidate.candidate_id) not in self._items:
                raise ContentAssistRepositoryError("candidate_not_found")
            self._items[str(candidate.candidate_id)] = candidate
            self._save()
            return candidate

    def list(self) -> list[ContentAssistCandidateV1]:
        with self._lock:
            return sorted(self._items.values(), key=lambda item: item.created_at)

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self._items = {
                item["candidate_id"]: ContentAssistCandidateV1.model_validate(item)
                for item in payload.get("candidates", [])
            }
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise ContentAssistRepositoryError("content_assist_repository_corrupt") from error

    def _save(self) -> None:
        payload = {
            "schema_version": 1,
            "candidates": [item.model_dump(mode="json") for item in self._items.values()],
        }
        fd, raw_path = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.root)
        temp_path = Path(raw_path)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            if temp_path.exists():
                temp_path.unlink()
