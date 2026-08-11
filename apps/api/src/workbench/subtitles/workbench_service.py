from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from workbench.services.project_service import ProjectService

from .models import SubtitleTimeline
from .workbench_models import (
    SubtitleCueV2,
    SubtitleLanguageTrack,
    SubtitleRenderMode,
    SubtitleStyleTemplate,
    SubtitleTranslationRequest,
    SubtitleTranslationResult,
    SubtitleWorkbenchCommand,
    SubtitleWorkbenchDocument,
)


class SubtitleWorkbenchError(ValueError):
    pass


class SubtitleWorkbenchConflict(SubtitleWorkbenchError):
    pass


class SubtitleWorkbenchService:
    """Revisioned subtitle editing service independent from subtitle generation.

    The legacy subtitle builder remains the source of initial timings. Every
    subsequent edit is stored as a complete, immutable revision so previews
    and exports can always reproduce the exact document that was approved.
    """

    def __init__(
        self,
        workspace_root: Path,
        project_dir_resolver: Callable[[UUID], str],
        projects: ProjectService | None = None,
        legacy_getter: Callable[[UUID], SubtitleTimeline] | None = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.project_dir_resolver = project_dir_resolver
        self.projects = projects
        self.legacy_getter = legacy_getter
        self._documents: dict[UUID, SubtitleWorkbenchDocument] = {}
        self._applied_commands: dict[UUID, dict[UUID, SubtitleWorkbenchDocument]] = {}

    def create(
        self,
        project_id: UUID,
        *,
        duration_ms: int = 0,
        language: str = "zh-CN",
        label: str = "中文",
        timeline: SubtitleTimeline | None = None,
    ) -> SubtitleWorkbenchDocument:
        if project_id in self._documents:
            return self._documents[project_id]
        seed = timeline
        if seed is None and self.legacy_getter is not None:
            try:
                seed = self.legacy_getter(project_id)
            except (KeyError, ValueError):
                seed = None
        if seed is not None:
            duration_ms = seed.duration_ms
        now = datetime.now(UTC).isoformat()
        style = SubtitleStyleTemplate(name="默认模板")
        cues = [
            SubtitleCueV2(
                id=cue.id,
                start_ms=cue.start_ms,
                end_ms=cue.end_ms,
                text=cue.text,
                source_word_indexes=cue.source_word_indexes,
            )
            for cue in (seed.cues if seed is not None else [])
        ]
        document = SubtitleWorkbenchDocument(
            duration_ms=duration_ms,
            default_style=style,
            templates=[style],
            tracks=[
                SubtitleLanguageTrack(
                    language=language,
                    label=label,
                    primary=True,
                    cues=cues,
                )
            ],
            updated_at=now,
        )
        document = self._with_hash(document)
        self._documents[project_id] = document
        self._persist(project_id, document)
        return document

    def get(self, project_id: UUID) -> SubtitleWorkbenchDocument:
        cached = self._documents.get(project_id)
        if cached is not None:
            return cached
        loaded = self._load_latest(project_id)
        if loaded is not None:
            self._documents[project_id] = loaded
            return loaded
        return self.create(project_id)

    def revisions(self, project_id: UUID) -> list[SubtitleWorkbenchDocument]:
        folder = self._folder(project_id)
        if not folder.is_dir():
            return [self.get(project_id)]
        documents: list[SubtitleWorkbenchDocument] = []
        for path in sorted(folder.glob("revision-*.json"), key=lambda item: item.name):
            documents.append(
                SubtitleWorkbenchDocument.model_validate_json(path.read_text(encoding="utf-8"))
            )
        return documents or [self.get(project_id)]

    def apply(
        self, project_id: UUID, command: SubtitleWorkbenchCommand
    ) -> SubtitleWorkbenchDocument:
        current = self.get(project_id)
        applied = self._applied_commands.setdefault(project_id, {})
        previous = applied.get(command.command_id)
        if previous is not None:
            return previous
        if command.expected_revision != current.revision:
            raise SubtitleWorkbenchConflict(
                f"expected revision {command.expected_revision}, current is {current.revision}"
            )
        candidate = deepcopy(current)
        self._apply_command(candidate, command)
        candidate.revision = current.revision + 1
        candidate.updated_at = datetime.now(UTC).isoformat()
        candidate.content_hash = ""
        candidate = self._with_hash(candidate)
        self._documents[project_id] = candidate
        applied[command.command_id] = candidate
        self._persist(project_id, candidate)
        return candidate

    def translate(
        self, project_id: UUID, request: SubtitleTranslationRequest
    ) -> SubtitleTranslationResult:
        current = self.get(project_id)
        primary = next(track for track in current.tracks if track.primary)
        existing = next(
            (track for track in current.tracks if track.language == request.language),
            None,
        )
        track = (
            deepcopy(existing)
            if existing is not None
            else SubtitleLanguageTrack(
                language=request.language,
                label=request.label,
                primary=False,
                visible=True,
                cues=[],
            )
        )
        translated = 0
        track.cues = []
        for cue in primary.cues:
            text = request.translations.get(str(cue.id))
            if text:
                translated += 1
            track.cues.append(
                cue.model_copy(update={"text": text or cue.text, "translation": cue.text})
            )
        command = SubtitleWorkbenchCommand(
            expected_revision=current.revision,
            kind="toggle_track",
            payload={
                "language": request.language,
                "visible": True,
                "track": track.model_dump(mode="json"),
            },
        )
        document = self.apply(project_id, command)
        return SubtitleTranslationResult(document=document, translated_cue_count=translated)

    def _apply_command(
        self, document: SubtitleWorkbenchDocument, command: SubtitleWorkbenchCommand
    ) -> None:
        payload = command.payload
        if command.kind == "set_render_mode":
            document.render_mode = SubtitleRenderMode(payload.get("render_mode", "soft"))
            return
        if command.kind == "upsert_template":
            template = SubtitleStyleTemplate.model_validate(payload.get("template", payload))
            document.templates = [item for item in document.templates if item.id != template.id]
            document.templates.append(template)
            if payload.get("default") is True:
                document.default_style = template
            return
        if command.kind == "toggle_track":
            replacement = payload.get("track")
            if replacement is not None:
                updated = SubtitleLanguageTrack.model_validate(replacement)
                document.tracks = [
                    item for item in document.tracks if item.language != updated.language
                ]
                document.tracks.append(updated)
            else:
                track = self._track(document, payload)
                track.visible = bool(payload.get("visible", track.visible))
            return
        track = self._track(document, payload)
        if command.kind == "set_style":
            style = SubtitleStyleTemplate.model_validate(payload.get("style", payload))
            cue = self._cue(track, payload)
            cue.style_override = style
            return
        if command.kind == "set_translation":
            cue = self._cue(track, payload)
            cue.translation = str(payload.get("translation", "")) or None
            return
        if command.kind == "set_word_highlight":
            cue = self._cue(track, payload)
            index = int(payload.get("word_index", -1))
            if index < 0 or index >= len(cue.words):
                raise SubtitleWorkbenchError("word_index is out of range")
            cue.words[index].highlighted = bool(payload.get("highlighted", True))
            return
        if command.kind == "update_cue":
            cue = self._cue(track, payload)
            if cue.locked:
                raise SubtitleWorkbenchError("locked cue cannot be edited")
            if "text" in payload:
                cue.text = str(payload["text"])
            if "line_breaks" in payload:
                cue.line_breaks = [int(item) for item in payload["line_breaks"]]
            return
        if command.kind == "retime_cue":
            cue = self._cue(track, payload)
            cue.start_ms = int(payload["start_ms"])
            cue.end_ms = int(payload["end_ms"])
            self._validate_cue(cue, document.duration_ms)
            return
        if command.kind == "split_cue":
            self._split_cue(track, payload, document.duration_ms)
            return
        if command.kind == "merge_cues":
            self._merge_cues(track, payload, document.duration_ms)
            return
        raise SubtitleWorkbenchError(f"unsupported subtitle command: {command.kind}")

    def _track(
        self, document: SubtitleWorkbenchDocument, payload: dict[str, object]
    ) -> SubtitleLanguageTrack:
        language = str(payload.get("language", ""))
        try:
            return next(track for track in document.tracks if track.language == language)
        except StopIteration as error:
            raise SubtitleWorkbenchError(f"subtitle track not found: {language}") from error

    def _cue(self, track: SubtitleLanguageTrack, payload: dict[str, object]) -> SubtitleCueV2:
        cue_id = str(payload.get("cue_id", ""))
        try:
            return next(cue for cue in track.cues if str(cue.id) == cue_id)
        except StopIteration as error:
            raise SubtitleWorkbenchError(f"subtitle cue not found: {cue_id}") from error

    def _split_cue(
        self, track: SubtitleLanguageTrack, payload: dict[str, object], duration_ms: int
    ) -> None:
        cue = self._cue(track, payload)
        raw_split_ms = payload.get("split_ms")
        if isinstance(raw_split_ms, bool) or not isinstance(raw_split_ms, (int, float, str)):
            raise SubtitleWorkbenchError("split_ms must be numeric")
        split_ms = int(raw_split_ms)
        if not cue.start_ms < split_ms < cue.end_ms:
            raise SubtitleWorkbenchError("split_ms must be inside cue range")
        left_text, right_text = self._split_text(cue.text)
        index = track.cues.index(cue)
        left = cue.model_copy(update={"end_ms": split_ms, "text": left_text})
        right = cue.model_copy(update={"id": uuid4(), "start_ms": split_ms, "text": right_text})
        self._validate_cue(left, duration_ms)
        self._validate_cue(right, duration_ms)
        track.cues[index : index + 1] = [left, right]

    def _merge_cues(
        self, track: SubtitleLanguageTrack, payload: dict[str, object], duration_ms: int
    ) -> None:
        raw_ids = payload.get("cue_ids", [])
        if not isinstance(raw_ids, list):
            raise SubtitleWorkbenchError("cue_ids must be a list")
        ids = [str(item) for item in raw_ids]
        selected = [cue for cue in track.cues if str(cue.id) in ids]
        if len(selected) != 2:
            raise SubtitleWorkbenchError("merge_cues requires exactly two cues")
        selected.sort(key=lambda item: item.start_ms)
        merged = selected[0].model_copy(
            update={
                "end_ms": selected[1].end_ms,
                "text": f"{selected[0].text} {selected[1].text}".strip(),
                "translation": " ".join(item.translation for item in selected if item.translation)
                or None,
            }
        )
        self._validate_cue(merged, duration_ms)
        track.cues = [cue for cue in track.cues if str(cue.id) not in ids]
        insert_at = next(
            (index for index, cue in enumerate(track.cues) if cue.start_ms > merged.start_ms),
            len(track.cues),
        )
        track.cues.insert(insert_at, merged)

    @staticmethod
    def _split_text(text: str) -> tuple[str, str]:
        midpoint = max(1, len(text) // 2)
        boundary = text.rfind(" ", 0, midpoint + 1)
        if boundary <= 0:
            boundary = midpoint
        return text[:boundary].strip(), text[boundary:].strip()

    @staticmethod
    def _validate_cue(cue: SubtitleCueV2, duration_ms: int) -> None:
        if cue.end_ms <= cue.start_ms or cue.end_ms > duration_ms:
            raise SubtitleWorkbenchError("cue range is outside document duration")

    def _folder(self, project_id: UUID) -> Path:
        project = self._project_root(project_id)
        folder = project / "06_字幕" / "workbench"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _project_root(self, project_id: UUID) -> Path:
        relative = Path(self.project_dir_resolver(project_id))
        root = (self.workspace_root / relative).resolve()
        workspace = self.workspace_root.resolve()
        if root != workspace and workspace not in root.parents:
            raise SubtitleWorkbenchError("project path escapes workspace root")
        return root

    def _load_latest(self, project_id: UUID) -> SubtitleWorkbenchDocument | None:
        folder = self._folder(project_id)
        revisions = sorted(folder.glob("revision-*.json"), key=lambda item: item.name)
        if not revisions:
            return None
        return SubtitleWorkbenchDocument.model_validate_json(
            revisions[-1].read_text(encoding="utf-8")
        )

    def _persist(self, project_id: UUID, document: SubtitleWorkbenchDocument) -> None:
        folder = self._folder(project_id)
        path = folder / f"revision-{document.revision:08d}.json"
        _atomic_write(path, (document.model_dump_json(indent=2) + "\n").encode("utf-8"))
        _atomic_write(
            folder / "current.json",
            (document.model_dump_json(indent=2) + "\n").encode("utf-8"),
        )

    @staticmethod
    def _with_hash(document: SubtitleWorkbenchDocument) -> SubtitleWorkbenchDocument:
        payload = document.model_dump(mode="json", exclude={"content_hash"})
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        return document.model_copy(update={"content_hash": digest})


def _atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)
