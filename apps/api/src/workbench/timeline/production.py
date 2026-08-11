from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from enum import StrEnum
from typing import Any, Literal, cast
from uuid import UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None


class TimelineError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ClipKind(StrEnum):
    SLIDE = "slide"
    NARRATION = "narration"
    PRESENTER = "presenter"
    SUBTITLE = "subtitle"
    EFFECT = "effect"
    OVERLAY = "overlay"
    MUSIC = "music"
    SFX = "sfx"
    MARKER = "marker"


class TimelineClip(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    track_id: UUID
    kind: ClipKind
    start_us: int = Field(ge=0)
    duration_us: int = Field(gt=0)
    source_in_us: int = Field(default=0, ge=0)
    source_duration_us: int | None = Field(default=None, gt=0)
    source_ref: str = Field(min_length=1, max_length=500)
    locked: bool = False
    link_group_id: UUID | None = None
    payload: dict[str, JsonValue] = Field(default_factory=dict)

    @property
    def end_us(self) -> int:
        return self.start_us + self.duration_us

    @model_validator(mode="after")
    def validate_source(self) -> TimelineClip:
        if (
            self.source_duration_us is not None
            and self.source_in_us + self.duration_us > self.source_duration_us
        ):
            raise ValueError("clip source range exceeds source duration")
        return self


class TimelineTrack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    kind: ClipKind
    name: str = Field(min_length=1, max_length=120)
    order: int = Field(ge=0)
    muted: bool = False
    locked: bool = False
    clips: list[TimelineClip] = Field(default_factory=list)


class TimelineMarker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    start_us: int = Field(ge=0)
    label: str = Field(min_length=1, max_length=120)
    kind: Literal["chapter", "review", "quality", "note"] = "note"


class ProductionTimeline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    project_id: UUID
    revision: int = Field(default=1, ge=1)
    fps: int = Field(default=30, gt=0, le=240)
    width: int = Field(default=1920, gt=0)
    height: int = Field(default=1080, gt=0)
    duration_us: int = Field(default=0, ge=0)
    tracks: list[TimelineTrack] = Field(default_factory=list)
    markers: list[TimelineMarker] = Field(default_factory=list)
    input_fingerprint: str = Field(default="", max_length=128)
    content_hash: str = Field(default="", pattern=r"^[0-9a-f]{64}$|^$")

    @model_validator(mode="after")
    def validate_timeline(self) -> ProductionTimeline:
        track_ids = {track.id for track in self.tracks}
        if len(track_ids) != len(self.tracks):
            raise ValueError("timeline track ids must be unique")
        clip_ids: set[UUID] = set()
        for track in self.tracks:
            previous_end = -1
            for clip in sorted(track.clips, key=lambda item: (item.start_us, str(item.id))):
                if clip.track_id != track.id:
                    raise ValueError("clip track_id must match containing track")
                if clip.id in clip_ids:
                    raise ValueError("timeline clip ids must be unique")
                clip_ids.add(clip.id)
                if track.kind is ClipKind.SLIDE and clip.start_us < previous_end:
                    previous = next(item for item in track.clips if item.id == clip.id)
                    if not bool(previous.payload.get("transition_overlap")):
                        raise ValueError(
                            "slide track clips cannot overlap without transition_overlap"
                        )
                previous_end = max(previous_end, clip.end_us)
        if self.duration_us and any(
            clip.end_us > self.duration_us for track in self.tracks for clip in track.clips
        ):
            raise ValueError("clip exceeds timeline duration")
        return self


class TimelineCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: UUID = Field(default_factory=uuid4)
    expected_revision: int = Field(ge=1)
    kind: Literal[
        "insert_clip",
        "move_clip",
        "trim_clip",
        "split_clip",
        "delete_clip",
        "set_clip_property",
        "reorder_track",
        "link_clips",
        "unlink_clips",
        "ripple_shift",
        "set_transition",
        "restore_revision",
    ]
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class TimelineCommandBatch(BaseModel):
    """An all-or-nothing sequence of commands for one editor revision."""

    model_config = ConfigDict(extra="forbid")

    batch_id: UUID = Field(default_factory=uuid4)
    expected_revision: int = Field(ge=1)
    commands: list[TimelineCommand] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_revision_sequence(self) -> TimelineCommandBatch:
        expected = self.expected_revision
        for command in self.commands:
            if command.expected_revision != expected:
                raise ValueError("batch command revisions must be sequential")
            expected += 1
        return self


class RenderNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    clip_id: UUID
    track_id: UUID
    kind: ClipKind
    start_us: int
    end_us: int
    source_ref: str
    cache_key: str
    depends_on: list[UUID] = Field(default_factory=list)


class RenderGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    project_id: UUID
    timeline_revision: int
    duration_us: int
    nodes: list[RenderNode]
    content_hash: str


def timeline_hash(timeline: ProductionTimeline) -> str:
    payload = timeline.model_dump(mode="json", exclude={"content_hash"})
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def with_content_hash(timeline: ProductionTimeline) -> ProductionTimeline:
    return timeline.model_copy(update={"content_hash": timeline_hash(timeline)})


class TimelineCompiler:
    def compile(self, timeline: ProductionTimeline) -> RenderGraph:
        validated = ProductionTimeline.model_validate(timeline.model_dump(mode="python"))
        nodes: list[RenderNode] = []
        prior_by_track: dict[UUID, UUID] = {}
        node_by_group: dict[UUID, list[UUID]] = {}
        ordered_tracks = sorted(validated.tracks, key=lambda item: item.order)
        for track in ordered_tracks:
            for clip in sorted(track.clips, key=lambda item: (item.start_us, str(item.id))):
                # Derive node identity from immutable inputs so compiling the
                # same revision yields a byte-stable RenderGraph and cache key.
                node_id = uuid5(
                    validated.project_id,
                    f"render-node:{validated.revision}:{track.id}:{clip.id}",
                )
                dependencies = [prior_by_track[track.id]] if track.id in prior_by_track else []
                if clip.link_group_id:
                    dependencies.extend(node_by_group.get(clip.link_group_id, []))
                cache_key = hashlib.sha256(
                    json.dumps(
                        {
                            "clip": clip.model_dump(mode="json"),
                            "timeline": validated.input_fingerprint,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
                nodes.append(
                    RenderNode(
                        id=node_id,
                        clip_id=clip.id,
                        track_id=track.id,
                        kind=clip.kind,
                        start_us=clip.start_us,
                        end_us=clip.end_us,
                        source_ref=clip.source_ref,
                        cache_key=cache_key,
                        depends_on=dependencies,
                    )
                )
                prior_by_track[track.id] = node_id
                if clip.link_group_id:
                    node_by_group.setdefault(clip.link_group_id, []).append(node_id)
        graph_payload = {
            "project_id": str(validated.project_id),
            "timeline_revision": validated.revision,
            "duration_us": validated.duration_us,
            "nodes": [node.model_dump(mode="json") for node in nodes],
        }
        content_hash = hashlib.sha256(
            json.dumps(graph_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return RenderGraph(
            project_id=validated.project_id,
            timeline_revision=validated.revision,
            duration_us=validated.duration_us,
            nodes=nodes,
            content_hash=content_hash,
        )


class TimelineEditor:
    def __init__(self, initial: ProductionTimeline) -> None:
        self._timeline = with_content_hash(initial)
        self._history: dict[int, ProductionTimeline] = {self._timeline.revision: self._timeline}
        self._command_results: dict[UUID, ProductionTimeline] = {}

    @property
    def timeline(self) -> ProductionTimeline:
        return self._timeline

    def apply(self, command: TimelineCommand) -> ProductionTimeline:
        previous_result = self._command_results.get(command.command_id)
        if previous_result is not None:
            return previous_result
        if command.expected_revision != self._timeline.revision:
            raise TimelineError("timeline_revision_conflict", "timeline revision does not match")
        next_value = self._apply_command(self._timeline, command)
        next_value = with_content_hash(
            next_value.model_copy(update={"revision": self._timeline.revision + 1})
        )
        self._timeline = next_value
        self._history[next_value.revision] = next_value
        self._command_results[command.command_id] = next_value
        return next_value

    def apply_batch(self, batch: TimelineCommandBatch) -> ProductionTimeline:
        """Validate and apply a command batch atomically.

        The working timeline is kept local until every command validates. A
        failed command therefore cannot leave a partially committed revision.
        """

        if batch.expected_revision != self._timeline.revision:
            raise TimelineError("timeline_revision_conflict", "timeline revision does not match")
        if any(command.command_id in self._command_results for command in batch.commands):
            raise TimelineError(
                "timeline_command_duplicate", "batch contains an already applied command"
            )

        working = self._timeline
        results: list[tuple[UUID, ProductionTimeline]] = []
        for command in batch.commands:
            if command.expected_revision != working.revision:
                raise TimelineError(
                    "timeline_revision_conflict", "batch command revision does not match"
                )
            next_value = with_content_hash(
                self._apply_command(working, command).model_copy(
                    update={"revision": working.revision + 1}
                )
            )
            working = next_value
            results.append((command.command_id, next_value))

        self._timeline = working
        for command_id, result in results:
            self._history[result.revision] = result
            self._command_results[command_id] = result
        return working

    def restore(self, revision: int, expected_revision: int) -> ProductionTimeline:
        return self.apply(
            TimelineCommand(
                expected_revision=expected_revision,
                kind="restore_revision",
                payload={"revision": revision},
            )
        )

    def _apply_command(
        self, timeline: ProductionTimeline, command: TimelineCommand
    ) -> ProductionTimeline:
        data = deepcopy(timeline.model_dump(mode="python"))
        tracks = data["tracks"]
        payload = cast(dict[str, Any], command.payload)
        if command.kind == "restore_revision":
            revision = int(payload.get("revision", 0))
            if revision not in self._history:
                raise TimelineError("timeline_revision_not_found", "timeline revision not found")
            return self._history[revision]
        if command.kind == "insert_clip":
            track_id = UUID(str(payload["track_id"]))
            clip_data = dict(payload["clip"])
            clip_data["track_id"] = track_id
            track = _track(tracks, track_id)
            track["clips"].append(clip_data)
        elif command.kind in {
            "move_clip",
            "trim_clip",
            "set_clip_property",
            "delete_clip",
            "split_clip",
        }:
            clip_id = UUID(str(payload["clip_id"]))
            track, clip = _find_clip(tracks, clip_id)
            if command.kind == "move_clip":
                clip["start_us"] = int(payload["start_us"])
                if "track_id" in payload:
                    new_track = _track(tracks, UUID(str(payload["track_id"])))
                    track["clips"].remove(clip)
                    clip["track_id"] = new_track["id"]
                    new_track["clips"].append(clip)
            elif command.kind == "trim_clip":
                clip["start_us"] = int(payload.get("start_us", clip["start_us"]))
                clip["duration_us"] = int(payload["duration_us"])
            elif command.kind == "set_clip_property":
                key = str(payload["key"])
                if key in {"id", "track_id", "start_us", "duration_us"}:
                    raise TimelineError(
                        "timeline_property_locked",
                        "clip structural property requires a dedicated command",
                    )
                clip.setdefault("payload", {})[key] = payload.get("value")
            elif command.kind == "delete_clip":
                track["clips"].remove(clip)
            else:
                split_at = int(payload["split_at_us"])
                if (
                    split_at <= clip["start_us"]
                    or split_at >= clip["start_us"] + clip["duration_us"]
                ):
                    raise TimelineError("timeline_split_invalid", "split point must be inside clip")
                first_duration = split_at - clip["start_us"]
                second = dict(clip)
                second["id"] = str(uuid4())
                second["start_us"] = split_at
                second["duration_us"] = clip["duration_us"] - first_duration
                clip["duration_us"] = first_duration
                track["clips"].append(second)
        elif command.kind == "reorder_track":
            track = _track(tracks, UUID(str(payload["track_id"])))
            track["order"] = int(payload["order"])
        elif command.kind in {"link_clips", "unlink_clips"}:
            group_id = UUID(str(payload.get("link_group_id") or uuid4()))
            for clip_id in payload.get("clip_ids", []):
                _find_clip(tracks, UUID(str(clip_id)))[1]["link_group_id"] = (
                    None if command.kind == "unlink_clips" else group_id
                )
        elif command.kind == "ripple_shift":
            track = _track(tracks, UUID(str(payload["track_id"])))
            from_us = int(payload["from_us"])
            delta_us = int(payload["delta_us"])
            for clip in track["clips"]:
                if clip["start_us"] >= from_us and not clip.get("locked", False):
                    clip["start_us"] += delta_us
        elif command.kind == "set_transition":
            clip = _find_clip(tracks, UUID(str(payload["clip_id"])))[1]
            clip.setdefault("payload", {})["transition_overlap"] = bool(
                payload.get("enabled", True)
            )
            clip["payload"]["transition"] = payload.get("transition", "crossfade")
        else:
            raise TimelineError("timeline_command_unknown", "unknown timeline command")
        return ProductionTimeline.model_validate(data)


def _track(tracks: list[dict[str, Any]], track_id: UUID) -> dict[str, Any]:
    for track in tracks:
        if UUID(str(track["id"])) == track_id:
            if track.get("locked"):
                raise TimelineError("timeline_track_locked", "timeline track is locked")
            return track
    raise TimelineError("timeline_track_not_found", "timeline track not found")


def _find_clip(
    tracks: list[dict[str, Any]], clip_id: UUID
) -> tuple[dict[str, Any], dict[str, Any]]:
    for track in tracks:
        for clip in track["clips"]:
            if UUID(str(clip["id"])) == clip_id:
                if clip.get("locked"):
                    raise TimelineError("timeline_clip_locked", "timeline clip is locked")
                return track, clip
    raise TimelineError("timeline_clip_not_found", "timeline clip not found")
